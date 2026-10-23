"""Host: one G4 session to set up + verify wenxi on Colab. Paid only with --execute-paid.
Stops before any prompt if preflight fails.

Canonical copy lives in scripts/ops/ (recycled from .cache 2026-10-21);
.cache only holds runtime data (input/, vendor/, per-session logs).
The 7 wenxi models are merged into the main Drive models tree, so restore
brings them down and there is no separate wenxi_models_copy stage.
Keeps: 120s retried Drive receipt reads + in-session smoke retry once.
"""
from __future__ import annotations
import argparse, hashlib, json, subprocess, sys, tarfile, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts/ops"; sys.path.insert(0, str(SCRIPTS))
from colab_h3_a100_ab_host import exec_file, run, snapshot, stop_and_verify
from colab_h3_g4_u02_host import STAGE_MARKERS
CONFIG = Path.home() / ".config/rclone-h3/rclone.conf"
BASE = ROOT / ".cache/colab_wenxi_setup"
INPUT = BASE / "input"
VENDOR = BASE / "vendor"
RESTORE = VENDOR
WHEEL_DIR = VENDOR
WENXI_INSTALL = SCRIPTS / "colab_h3_wenxi_install.py"
WENXI_PREFLIGHT = SCRIPTS / "colab_h3_wenxi_preflight.py"
WENXI_PHASE = SCRIPTS / "colab_h3_wenxi_phase.py"
REMOTE_BASE = "h3drive_h3:comfyui-h3-colab-dedicated/wenxi-setup"

def exec_retry(session, path, timeout, log, **env):
    for attempt in range(2):
        try: exec_file(session, path, timeout, log, **env); return
        except Exception:
            text = log.read_text(errors="replace") if log.is_file() else ""
            if attempt == 0 and any(m in text for m in ("WebSocketConnectionClosedException","SSLError","Connection was lost","SSLEOFError")):
                time.sleep(10); continue
            raise

def remote_bytes(path, timeout=120):
    # Drive reads can stall for tens of seconds; never gate a warm session
    # on a short-timeout receipt read (2026-10-21 smoke died on a 15s cat
    # before the phase even started, and the host stopped the session).
    for i in range(3):
        try:
            r = subprocess.run(["rclone","cat",path,"--config",str(CONFIG)],capture_output=True,check=True,timeout=timeout)
            return r.stdout
        except Exception:
            if i == 2: raise
            time.sleep(5)

def remote_json(path):
    return json.loads(remote_bytes(path))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--execute-paid", action="store_true")
    ap.add_argument("--safety-hours", type=float, default=3.0); args = ap.parse_args()
    wheels = list(WHEEL_DIR.glob("sageattention-2.2.0-cp313-cp313-linux_x86_64.whl"))
    required = [CONFIG, RESTORE/"colab-h3-rclone.gz", SCRIPTS/"h3_g4_identity.py", SCRIPTS/"colab_h3_preinstall_torch.py",
        SCRIPTS/"colab_h3_restore.py", SCRIPTS/"h3_g4_setup.py", SCRIPTS/"h3_a100_phase_receipt.py",
        SCRIPTS/"colab_h3_paid_watchdog.sh", WENXI_INSTALL, WENXI_PREFLIGHT, WENXI_PHASE, INPUT/"manifest.json"]
    missing = [str(p) for p in required if not p.is_file()]
    if missing or len(wheels) != 1: raise RuntimeError(f"missing inputs {missing} wheels={wheels}")
    wheel = wheels[0]; wheel_sha = hashlib.sha256(wheel.read_bytes()).hexdigest()
    session = "h3-wenxi-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    remote = f"{REMOTE_BASE}/{session}"
    if not args.execute_paid:
        print(json.dumps({"ready": True, "paid_started": False, "session": session, "remote": remote})); return
    logdir = BASE / session; logdir.mkdir(parents=True, exist_ok=False)
    snapshots = logdir / "cu-snapshots.jsonl"
    before = snapshot(snapshots, "before_assignment")
    sessions = run(["colab","sessions"], logdir/"sessions-before.log", timeout=30)
    if before["active"] or before["rate"] or "No active sessions" not in sessions: raise RuntimeError("Colab not idle")
    (logdir/"trial-inputs.json").write_text(json.dumps({"session":session,"remote":remote,"wheel_sha256":wheel_sha,"before":before},indent=2)+"\n")
    created=False; watcher=None; started=time.monotonic(); deadline=datetime.now(timezone.utc)+timedelta(hours=args.safety_hours)
    try:
        created=True
        run(["colab","new","--session",session,"--gpu","G4"], logdir/"assignment.log", timeout=180)
        assigned = snapshot(snapshots, "assigned")
        if assigned["active"] != 1 or assigned["rate"] <= 0: raise RuntimeError("G4 assignment not confirmed")
        wl = (logdir/"watchdog.log").open("w")
        try: watcher = subprocess.Popen(["bash",str(SCRIPTS/"colab_h3_paid_watchdog.sh"),session,deadline.isoformat()],stdin=subprocess.DEVNULL,stdout=wl,stderr=subprocess.STDOUT,start_new_session=True)
        finally: wl.close()
        time.sleep(0.2)
        if watcher.poll() is not None: raise RuntimeError("watchdog exited")
        print("WENXI_SESSION", session, "remote", remote, "rate", assigned["rate"], flush=True)
        uploads = [(CONFIG,"/content/rclone.conf"),(RESTORE/"colab-h3-rclone.gz","/content/rclone.gz"),
            (SCRIPTS/"h3_a100_phase_receipt.py","/content/h3_a100_phase_receipt.py"),
            (WENXI_INSTALL,"/content/wenxi_install.py"),(WENXI_PREFLIGHT,"/content/wenxi_preflight.py"),
            (WENXI_PHASE,"/content/wenxi_phase.py"),
            (wheel,"/content/"+wheel.name)]
        for src,dst in uploads: run(["colab","upload","--session",session,str(src),dst], logdir/("upload-"+src.name+".log"), timeout=300)
        bundle = logdir/"wenxi_input.tar.gz"
        with tarfile.open(bundle,"w:gz") as tar:
            for p in sorted(INPUT.iterdir()): tar.add(p, arcname=p.name)
        last=None
        for attempt in range(3):
            try: run(["colab","upload","--session",session,str(bundle),"/content/wenxi_input.tar.gz"], logdir/f"upload-bundle-{attempt}.log", timeout=300); last=None; break
            except Exception as e: last=e; time.sleep(5)
        if last is not None: raise last
        mover = logdir/"mover.py"; mover.write_text("import tarfile,pathlib\ndst=pathlib.Path('/content/wenxi_setup/input'); dst.mkdir(parents=True,exist_ok=True)\ntarfile.open('/content/wenxi_input.tar.gz').extractall(dst)\nprint('MOVED',len(list(dst.iterdir())))\n")
        exec_retry(session, mover, 60, logdir/"mover.log")
        stages = (("identity",SCRIPTS/"h3_g4_identity.py",60,{}),("preinstall",SCRIPTS/"colab_h3_preinstall_torch.py",720,{}),
                  ("restore",SCRIPTS/"colab_h3_restore.py",2400,{}),("setup",SCRIPTS/"h3_g4_setup.py",900,{"H3_G4_WHEEL_SHA256":wheel_sha}))
        for name,path,timeout,env in stages:
            began=time.monotonic(); exec_retry(session,path,timeout,logdir/f"{name}.log",**env)
            if STAGE_MARKERS[name] not in (logdir/f"{name}.log").read_text(errors="replace"): raise RuntimeError(f"{name} no marker")
            st=snapshot(snapshots,name); (logdir/"stage-timing.jsonl").open("a").write(json.dumps({"stage":name,"elapsed_s":round(time.monotonic()-began,2),"rate":st["rate"],"balance":st["balance"]})+"\n")
        # Wenxi 7 models are merged into the main models tree and already
        # arrived with restore; no separate copy stage. Preflight below
        # hashes the restored local tree and is the verification gate.
        print("WENXI_MODELS_MERGED_IN_RESTORE no separate copy stage", flush=True)
        (logdir/"stage-timing.jsonl").open("a").write(json.dumps({"stage":"models_copy","elapsed_s":0,"note":"merged_in_restore"})+"\n")
        # install SelfLift + native allocator restart
        began=time.monotonic(); exec_retry(session, WENXI_INSTALL, 900, logdir/"wenxi_install.log")
        txt=(logdir/"wenxi_install.log").read_text(errors="replace")
        if "WENXI_NATIVE_ALLOCATOR_OK" not in txt: raise RuntimeError("native allocator not verified")
        st=snapshot(snapshots,"wenxi_install"); (logdir/"stage-timing.jsonl").open("a").write(json.dumps({"stage":"wenxi_install","elapsed_s":round(time.monotonic()-began,2),"balance":st["balance"]})+"\n")
        # preflight (expected to publish JSON even on fail)
        try: exec_retry(session, WENXI_PREFLIGHT, 900, logdir/"preflight.log", H3_WENXI_REMOTE=remote)
        except Exception as e: print("PREFLIGHT_EXEC_ENDED", e, flush=True)
        report = remote_json(f"{remote}/preflight.json")
        (logdir/"preflight.json").write_text(json.dumps(report,indent=2)+"\n")
        print("HOST_PREFLIGHT", json.dumps({"all_match":report.get("all_match"),"device":report.get("device"),"missing_nodes":report.get("missing_nodes"),"missing_models":report.get("missing_models"),"bad_sha":report.get("bad_sha")}), flush=True)
        if not report.get("all_match"): print("STOP_NO_SMOKE_PREFLIGHT_FAILED", flush=True)
        else:
            print("HOST_PREFLIGHT_VERIFIED", len(report.get("models",[])), flush=True)
            began=time.monotonic(); phase_log=logdir/"SMOKE.log"
            # Precompute the preflight manifest sha with a long, retried
            # Drive read and hand it to exec_file, so it never does its
            # own 15s remote_manifest_sha256 fetch on a warm session.
            pre_sha = hashlib.sha256(remote_bytes(f"{remote}/preflight.json")).hexdigest()
            receipt=None; last_err=None
            for attempt in range(2):
                try: exec_file(session, WENXI_PHASE, 4200, phase_log, phase_label="SMOKE", receipt_path=f"{remote}/SMOKE/phase.json", input_manifest_sha256=pre_sha, H3_WENXI_REMOTE=remote)
                except Exception as e: print(f"SMOKE_EXEC_ENDED attempt={attempt}", e, flush=True); last_err=e
                try: receipt = remote_json(f"{remote}/SMOKE/phase.json"); break
                except Exception as e:
                    last_err=e; print(f"SMOKE_RECEIPT_MISSING attempt={attempt}", e, flush=True); time.sleep(10)
            if receipt is None: raise RuntimeError(f"smoke produced no receipt after retries: {last_err}")
            if receipt.get("state")!="success" or receipt.get("archive_state")!="verified" or receipt.get("session_id")!=session or receipt.get("label")!="SMOKE" or receipt.get("input_manifest_sha256")!=pre_sha:
                raise RuntimeError(f"smoke receipt mismatch: {receipt}")
            (logdir/"phase-receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
            st=snapshot(snapshots,"after_SMOKE"); (logdir/"stage-timing.jsonl").open("a").write(json.dumps({"stage":"SMOKE","elapsed_s":round(time.monotonic()-began,2),"balance":st["balance"]})+"\n")
            print("SMOKE_REMOTE", f"{remote}/SMOKE", "prompt_id", receipt.get("prompt_id"), flush=True)
    finally:
        if created:
            try: stop_and_verify(session, logdir, watcher)
            finally:
                try: run(["colab","log","--session",session,"--output",str(logdir/"colab-session.jsonl")], timeout=120)
                except Exception as e: print("SESSION_LOG_UNAVAILABLE", e, flush=True)
                try: run(["rclone","copy",remote,str(logdir/"evidence"),"--config",str(CONFIG)], timeout=600)
                except Exception as e: print("EVIDENCE_PULL_UNAVAILABLE", e, flush=True)
                (logdir/"host-wall-s.txt").write_text(f"{round(time.monotonic()-started,2)}\n")
if __name__ == "__main__": main()
