#!/usr/bin/env python3
"""Host: one G4 session renders a lihun wenxi batch end to end.

Single supervisor process per docs/ops/2026-10-21-colab-session-loss-
and-guard.md: create session -> restore/install -> batch render in the
guest -> archive every finished unit from Drive to Feiniu as it lands
-> stop the session -> verify Active=0. An account-level orphan guard
(colab_orphan_guard.sh, AUTO_UNASSIGN=1) watches the whole run; this
process touches its heartbeat on every poll.

Paid only with --execute-paid. Feiniu batch name is fixed at import
time below (BATCH); episode/unit subfolders come from the manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "ops"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "src"))

from colab_h3_a100_ab_host import (  # noqa: E402
    exec_file,
    run,
    snapshot,
    stop_and_verify,
)
from colab_h3_g4_u02_host import STAGE_MARKERS  # noqa: E402
from comfy_orch.feiniu_archive import archive_named_files  # noqa: E402

CONFIG = Path.home() / ".config/rclone-h3/rclone.conf"
BASE = ROOT / ".cache/colab_wenxi_setup"
INPUT = ROOT / ".cache/lihun_v23_colab/input"
VENDOR = BASE / "vendor"
WENXI_INSTALL = SCRIPTS / "colab_h3_wenxi_install.py"
BATCH_PHASE = SCRIPTS / "colab_h3_wenxi_batch_phase.py"
KEEPER = SCRIPTS / "colab_heartbeat_keeper.sh"
GUARDIAN = SCRIPTS / "colab_session_guardian.sh"
REMOTE_BASE = "h3drive_h3:comfyui-h3-colab-dedicated/lihun-v23"
FEINIU_BATCH = "离婚后（10.22）"
HEARTBEAT = ROOT / "runs/lihun_v23_colab_heartbeat"


def remote_bytes(path: str, timeout: int = 60) -> bytes:
    # Single attempt: the archiver polls every pending tag each round,
    # so a missing receipt must fail fast (the next round retries).
    # Retrying here made one poll round take ~15 minutes.
    r = subprocess.run(["rclone", "cat", path, "--config", str(CONFIG)],
                       capture_output=True, check=True, timeout=timeout)
    return r.stdout


def remote_json(path: str):
    return json.loads(remote_bytes(path))


def exec_retry(session, path, timeout, log, **env):
    for attempt in range(3):
        try:
            exec_file(session, path, timeout, log, **env)
            return
        except Exception as exc:
            text = log.read_text(errors="replace") if log.is_file() else ""
            retryable = isinstance(exc, TimeoutError) or any(m in text for m in (
                "WebSocketConnectionClosedException", "SSLError",
                "Connection was lost", "SSLEOFError"))
            if attempt < 2 and retryable:
                print(f"EXEC_RETRY {path.name} attempt={attempt + 1} "
                      f"error={type(exc).__name__}: {exc}", flush=True)
                time.sleep(10)
                continue
            raise


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute-paid", action="store_true")
    ap.add_argument("--safety-hours", type=float, default=5.0)
    ap.add_argument("--adopt-session",
                    help="reuse this live session instead of creating one "
                         "(env stages already done are skipped)")
    ap.add_argument("--adopt-logdir", type=Path,
                    help="logdir of the original host run (stage markers)")
    ap.add_argument("--extra-input", type=Path, action="append", default=[],
                    help="additional input bundle dir(s) rendered after "
                         "the primary one, in the same session")
    ap.add_argument("--no-stop", action="store_true",
                    help="leave the session running at the end "
                         "(heartbeat keeper + guards stay armed)")
    ap.add_argument("--done-remote", action="append", default=[],
                    help="Drive remote of a previous session whose "
                         "success receipts should be skipped, not "
                         "re-rendered (repeatable)")
    ap.add_argument("--allow-concurrent", action="store_true",
                    help="skip the account-idle gate when creating a "
                         "session (multi-session parallel production; "
                         "each session is billed separately)")
    args = ap.parse_args()

    bundle_dirs = [INPUT] + list(args.extra_input)
    units = []
    for d in bundle_dirs:
        units += json.loads((d / "units.json").read_text())["units"]
    wheels = list(VENDOR.glob("sageattention-2.2.0-cp313-cp313-linux_x86_64.whl"))
    required = [CONFIG, VENDOR / "colab-h3-rclone.gz",
                SCRIPTS / "h3_g4_identity.py",
                SCRIPTS / "colab_h3_preinstall_torch.py",
                SCRIPTS / "colab_h3_restore.py",
                SCRIPTS / "h3_g4_setup.py",
                SCRIPTS / "h3_a100_phase_receipt.py",
                SCRIPTS / "colab_h3_paid_watchdog.sh",
                WENXI_INSTALL, BATCH_PHASE, KEEPER, GUARDIAN,
                SCRIPTS / "colab_takeover_rebuild.py",
                SCRIPTS / "colab_keepalive_probe.py", INPUT / "units.json"]
    missing = [str(p) for p in required if not p.is_file()]
    if missing or len(wheels) != 1:
        raise RuntimeError(f"missing inputs {missing} wheels={wheels}")
    wheel = wheels[0]
    wheel_sha = hashlib.sha256(wheel.read_bytes()).hexdigest()

    adopt = bool(args.adopt_session)
    if adopt:
        session = args.adopt_session
        logdir = args.adopt_logdir or (BASE / session)
        if not logdir.is_dir():
            raise RuntimeError(f"adopt logdir missing: {logdir}")
    else:
        session = "h3-lihun-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        logdir = BASE / session
    remote = f"{REMOTE_BASE}/{session}"
    if not args.execute_paid:
        print(json.dumps({"ready": True, "paid_started": False,
                          "session": session, "remote": remote,
                          "units": len(units), "adopt": adopt},
                         ensure_ascii=False))
        return 0

    snapshots = logdir / "cu-snapshots.jsonl"
    done_stages = set()
    if adopt:
        timing = logdir / "stage-timing.jsonl"
        if timing.is_file():
            for line in timing.read_text().splitlines():
                try:
                    done_stages.add(json.loads(line)["stage"])
                except Exception:
                    pass
        print(f"ADOPT {session} done_stages={sorted(done_stages)}",
              flush=True)
    else:
        logdir.mkdir(parents=True, exist_ok=False)
        before = snapshot(snapshots, "before_assignment")
        sessions = run(["colab", "sessions"], logdir / "sessions-before.log",
                       timeout=30)
        if not args.allow_concurrent and (
                before["active"] or before["rate"]
                or "No active sessions" not in sessions):
            raise RuntimeError("Colab not idle")
    (logdir / "trial-inputs.json").write_text(json.dumps(
        {"session": session, "remote": remote, "wheel_sha256": wheel_sha,
         "adopt": adopt, "units": [u["tag"] for u in units]},
        ensure_ascii=False, indent=2) + "\n")

    created = False
    watcher = None
    guard = None
    keeper = None
    guardian = None
    keeper_stop = logdir / "KEEPER_STOP"
    started = time.monotonic()
    deadline = datetime.now(timezone.utc) + timedelta(hours=args.safety_hours)
    archived: dict[str, str] = {}
    failed_units: dict[str, str] = {}
    stop_archive = threading.Event()

    def touch_heartbeat():
        HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
        HEARTBEAT.write_text(datetime.now(timezone.utc).isoformat())

    def archiver():
        pending = {u["tag"]: u for u in units}
        while not stop_archive.is_set() or pending:
            touch_heartbeat()
            for tag in list(pending):
                unit = pending[tag]
                try:
                    receipt = remote_json(f"{remote}/{tag}/phase.json")
                except Exception:
                    continue
                if receipt.get("state") == "failed":
                    failed_units[tag] = str(receipt.get("error"))
                    del pending[tag]
                    print(f"ARCHIVE_SEEN_FAILED {tag}", flush=True)
                    continue
                if receipt.get("state") != "success":
                    continue
                if receipt.get("skipped_done_remote"):
                    archived[tag] = (
                        f"prev:{receipt['skipped_done_remote']}")
                    del pending[tag]
                    print(f"ARCHIVE_SKIP_DONE_REMOTE {tag} -> "
                          f"{receipt['skipped_done_remote']}", flush=True)
                    continue
                dest = logdir / "units" / tag
                dest.mkdir(parents=True, exist_ok=True)
                run(["rclone", "copy", f"{remote}/{tag}", str(dest),
                     "--config", str(CONFIG)],
                    logdir / f"pull-{tag}.log", timeout=900)
                payloads = {}
                for name in (receipt["mp4_file"], receipt["latent_file"],
                             "prompt_h3.txt", "run_meta.json"):
                    payloads[name] = (dest / name).read_bytes()
                remote_dir = archive_named_files(
                    payloads, batch=FEINIU_BATCH, episode=unit["episode"],
                    unit=f"{unit['unit']}-WENXI")
                archived[tag] = remote_dir
                del pending[tag]
                print(f"FEINIU {tag} -> {remote_dir}", flush=True)
            if stop_archive.is_set() and not pending:
                break
            if not stop_archive.is_set():
                stop_archive.wait(45)
            else:
                break
        print(f"ARCHIVER_DONE archived={len(archived)} "
              f"failed={len(failed_units)}", flush=True)

    def wait_for_bundle(tags, timeout_s):
        deadline_wait = time.monotonic() + timeout_s
        while True:
            touch_heartbeat()
            if all(tag in archived or tag in failed_units for tag in tags):
                return True
            remaining = deadline_wait - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(15, remaining))

    arch_thread = None
    try:
        created = True
        if adopt:
            subprocess.run(["pkill", "-f",
                            f"colab_h3_paid_watchdog.sh {session}"],
                           check=False)
            assigned = snapshot(snapshots, "adopted")
            if assigned["active"] != 1:
                raise RuntimeError("adopted session is not active")
            print(f"ADOPTED {session} rate={assigned['rate']}", flush=True)
        else:
            run(["colab", "new", "--session", session, "--gpu", "G4"],
                logdir / "assignment.log", timeout=180)
            assigned = snapshot(snapshots, "assigned")
            if args.allow_concurrent:
                confirmed = (assigned["active"] > before["active"]
                             and assigned["rate"] > before["rate"])
            else:
                confirmed = (assigned["active"] == 1
                             and assigned["rate"] > 0)
            if not confirmed:
                raise RuntimeError("G4 assignment not confirmed")
        wl = (logdir / "watchdog.log").open("w")
        try:
            watcher = subprocess.Popen(
                ["bash", str(SCRIPTS / "colab_h3_paid_watchdog.sh"),
                 session, deadline.isoformat()],
                stdin=subprocess.DEVNULL, stdout=wl,
                stderr=subprocess.STDOUT, start_new_session=True)
        finally:
            wl.close()
        print("LIHUN_SESSION", session, "remote", remote,
              "rate", assigned["rate"], "units", len(units), flush=True)

        keeper_stop.unlink(missing_ok=True)
        keeper_out = (logdir / "heartbeat-keeper.out").open("w")
        try:
            keeper = subprocess.Popen(
                ["bash", str(KEEPER), session, str(keeper_stop), "120"],
                stdin=subprocess.DEVNULL, stdout=keeper_out,
                stderr=subprocess.STDOUT, start_new_session=True)
        finally:
            keeper_out.close()
        time.sleep(0.2)
        if keeper.poll() is not None:
            raise RuntimeError("heartbeat keeper exited at startup")
        print(f"KEEPER_STARTED pid={keeper.pid} stop_file={keeper_stop}",
              flush=True)

        # The guard's dead-man switch must watch the keeper's real
        # activity log, not a file the supervisor touches: supervisor
        # death with a live keeper is recoverable, keeper death is not.
        touch_heartbeat()
        guard_env = dict(os.environ)
        guard_env.update({
            "HEARTBEAT": str(ROOT / "runs/colab_heartbeat_keeper.log"),
            "AUTO_UNASSIGN": "1", "POLL_S": "60",
            "LOG": str(ROOT / "runs/colab_orphan_guard.log")})
        guard = subprocess.Popen(
            ["bash", str(SCRIPTS / "colab_orphan_guard.sh")],
            env=guard_env,
            stdin=subprocess.DEVNULL,
            stdout=(logdir / "orphan-guard.log").open("w"),
            stderr=subprocess.STDOUT, start_new_session=True)

        # Session guardian: rotate the 1h runtime-proxy token before
        # it expires and rebuild the roster within a minute if the
        # CLI prunes it anyway (see colab_session_guardian.sh).
        guardian = subprocess.Popen(
            ["bash", str(GUARDIAN), session,
             str(logdir / "sessions_backup.json"), "2400", "60"],
            stdin=subprocess.DEVNULL,
            stdout=(logdir / "session-guardian.out").open("w"),
            stderr=subprocess.STDOUT, start_new_session=True)
        print(f"GUARDIAN_STARTED pid={guardian.pid}", flush=True)

        uploads = [(CONFIG, "/content/rclone.conf"),
                   (VENDOR / "colab-h3-rclone.gz", "/content/rclone.gz"),
                   (SCRIPTS / "h3_a100_phase_receipt.py",
                    "/content/h3_a100_phase_receipt.py"),
                   (WENXI_INSTALL, "/content/wenxi_install.py"),
                   (BATCH_PHASE, "/content/wenxi_batch_phase.py")]
        # Always upload the wheel: an adopted session may have been
        # created by a host that died before this upload landed, and
        # the setup stage requires the file at /content/<wheel>.
        uploads.append((wheel, "/content/" + wheel.name))
        for src, dst in uploads:
            last = None
            for attempt in range(3):
                try:
                    run(["colab", "upload", "--session", session,
                         str(src), dst],
                        logdir / ("upload-" + src.name + ".log"),
                        timeout=300)
                    last = None
                    break
                except Exception as exc:
                    last = exc
                    print(f"UPLOAD_RETRY {src.name} attempt={attempt} "
                          f"{type(exc).__name__}: {exc}", flush=True)
                    time.sleep(5)
            if last is not None:
                raise last

        stages = (("identity", SCRIPTS / "h3_g4_identity.py", 60, {}),
                  ("preinstall", SCRIPTS / "colab_h3_preinstall_torch.py", 720, {}),
                  ("restore", SCRIPTS / "colab_h3_restore.py", 2400, {}),
                  ("setup", SCRIPTS / "h3_g4_setup.py", 900,
                   {"H3_G4_WHEEL_SHA256": wheel_sha}))
        for name, path, timeout, env in stages:
            if name in done_stages:
                print(f"STAGE_SKIP {name} (adopt)", flush=True)
                continue
            began = time.monotonic()
            exec_retry(session, path, timeout, logdir / f"{name}.log", **env)
            if STAGE_MARKERS[name] not in (logdir / f"{name}.log").read_text(
                    errors="replace"):
                raise RuntimeError(f"{name} no marker")
            st = snapshot(snapshots, name)
            (logdir / "stage-timing.jsonl").open("a").write(json.dumps(
                {"stage": name, "elapsed_s": round(time.monotonic() - began, 2),
                 "rate": st["rate"], "balance": st["balance"]}) + "\n")
            print(f"STAGE_OK {name}", flush=True)

        install_log = logdir / "wenxi_install.log"
        if adopt and install_log.is_file() and \
                "WENXI_NATIVE_ALLOCATOR_OK" in install_log.read_text(
                    errors="replace"):
            print("STAGE_SKIP wenxi_install (adopt)", flush=True)
        else:
            exec_retry(session, WENXI_INSTALL, 900, install_log)
            txt = install_log.read_text(errors="replace")
            if "WENXI_NATIVE_ALLOCATOR_OK" not in txt:
                raise RuntimeError("native allocator not verified")
            snapshot(snapshots, "wenxi_install")
            print("STAGE_OK wenxi_install", flush=True)

        arch_thread = threading.Thread(target=archiver, daemon=True)
        arch_thread.start()
        for idx, bdir in enumerate(bundle_dirs):
            bundle = logdir / f"lihun_input_{idx}.tar.gz"
            with tarfile.open(bundle, "w:gz") as tar:
                for p in sorted(bdir.rglob("*")):
                    if p.is_file():
                        tar.add(p, arcname=str(p.relative_to(bdir)))
            last = None
            for attempt in range(3):
                try:
                    run(["colab", "upload", "--session", session, str(bundle),
                         "/content/lihun_input.tar.gz"],
                        logdir / f"upload-bundle{idx}-{attempt}.log",
                        timeout=600)
                    last = None
                    break
                except Exception as e:
                    last = e
                    time.sleep(5)
            if last is not None:
                raise last
            mover = logdir / f"mover{idx}.py"
            mover.write_text(
                "import tarfile,pathlib\n"
                "dst=pathlib.Path('/content/wenxi_setup/input'); "
                "dst.mkdir(parents=True,exist_ok=True)\n"
                "tarfile.open('/content/lihun_input.tar.gz').extractall(dst)\n"
                "print('MOVED',len(list(dst.rglob('*'))))\n")
            # A mover exec can queue behind a busy guest kernel (the
            # batch phase keeps rendering server-side even if an exec
            # returns early), so 60s is far too tight here.
            exec_retry(session, mover, 1800, logdir / f"mover{idx}.log")
            bundle_units = json.loads((bdir / "units.json").read_text())["units"]
            bundle_tags = [u["tag"] for u in bundle_units]
            batch_complete = False
            for exec_attempt in range(12):
                began = time.monotonic()
                try:
                    exec_file(session, BATCH_PHASE, 14400,
                              logdir / f"batch_phase_{idx}.log",
                              H3_WENXI_REMOTE=remote,
                              H3_DONE_REMOTES=",".join(args.done_remote))
                except Exception as exc:
                    print(f"BATCH_EXEC_ERROR idx={idx} "
                          f"attempt={exec_attempt} "
                          f"{type(exc).__name__}: {exc}", flush=True)
                batch_log = logdir / f"batch_phase_{idx}.log"
                batch_txt = (batch_log.read_text(errors="replace")
                             if batch_log.is_file() else "")
                print(f"BATCH_EXEC_ENDED idx={idx} attempt={exec_attempt}",
                      f"elapsed={round(time.monotonic() - began, 1)}",
                      flush=True)
                if "BATCH_PHASE_DONE" in batch_txt and wait_for_bundle(
                        bundle_tags, timeout_s=0):
                    batch_complete = True
                    break
                if wait_for_bundle(bundle_tags, timeout_s=300):
                    batch_complete = True
                    break
                print(f"BATCH_RESUME idx={idx} attempt={exec_attempt} "
                      f"missing="
                      f"{[t for t in bundle_tags if t not in archived and t not in failed_units]}",
                      flush=True)
            if not batch_complete:
                raise RuntimeError(
                    f"batch phase {idx} did not reach terminal receipts")
        stop_archive.set()
        arch_thread.join(timeout=1800)
        snapshot(snapshots, "after_batch")
        if len(archived) != len(units) or failed_units:
            raise RuntimeError(
                f"archive incomplete archived={len(archived)}/{len(units)} "
                f"failed={failed_units}")
        print(f"LIHUN_BATCH_DONE units={len(archived)} "
              f"batch={FEINIU_BATCH}", flush=True)
        (logdir / "archived.json").write_text(json.dumps(
            {"session": session, "feiniu_batch": FEINIU_BATCH,
             "archived": archived}, ensure_ascii=False, indent=2) + "\n")
        return 0
    finally:
        stop_archive.set()
        if arch_thread is not None:
            arch_thread.join(timeout=120)
        if created and args.no_stop:
            kept = snapshot(snapshots, "kept_alive")
            print(f"SESSION_KEPT {session} balance={kept['balance']} "
                  f"rate={kept['rate']} (guards + heartbeat keeper stay "
                  f"armed; stop explicitly when done)", flush=True)
        elif created:
            try:
                stop_and_verify(session, logdir, watcher)
            finally:
                try:
                    run(["colab", "log", "--session", session, "--output",
                         str(logdir / "colab-session.jsonl")], timeout=120)
                except Exception as e:
                    print("SESSION_LOG_UNAVAILABLE", e, flush=True)
                try:
                    run(["rclone", "copy", remote, str(logdir / "evidence"),
                         "--config", str(CONFIG)], timeout=600)
                except Exception as e:
                    print("EVIDENCE_PULL_UNAVAILABLE", e, flush=True)
                (logdir / "host-wall-s.txt").write_text(
                    f"{round(time.monotonic() - started, 2)}\n")
                after = snapshot(snapshots, "after_stop")
                print(f"HOST_DONE balance={after['balance']} "
                      f"active={after['active']} rate={after['rate']}",
                      flush=True)
        if keeper is not None and not args.no_stop:
            keeper_stop.write_text(
                datetime.now(timezone.utc).isoformat() + "\n")
            if keeper.poll() is None:
                try:
                    keeper.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    keeper.terminate()
        if guardian is not None and not args.no_stop \
                and guardian.poll() is None:
            guardian.terminate()
        if guard is not None and guard.poll() is None and not args.no_stop:
            guard.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
