"""One supervised Colab G4 U02 trial; no automatic retry and no CU cap.

The safety deadline only prevents an unattended paid assignment from persisting.
Run only with --execute-paid after reviewing the frozen inputs and Drive state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from colab_h3_a100_ab_host import exec_file, run, snapshot, stop_and_verify


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts/ops"
BACKUP = Path("/mnt/d/comfyui-h3-backups/rental-20260924-5090")
RESTORE = BACKUP / "colab-stage2/control-scripts"
REFERENCE = BACKUP / "a100-perf-pilot/h3-a100-ab-20260925-163222/evidence/C1/submitted_graph.json"
CONFIG = Path.home() / ".config/rclone-h3/rclone.conf"
WHEEL_DIR = BACKUP / "g4-u02/wheels"
REMOTE_BASE = "h3drive_h3:comfyui-h3-colab-dedicated/standard-v1/runs/ep04/u02"
RESTORED_GPU_ADAPT_SHA256 = "a2333220eafb3a90d333312883a5e1875a5b95cf991e994e0ec27bf8bfa4efaa"
STAGE_MARKERS = {
    "identity": "G4_IDENTITY_OK",
    "preinstall": '"probe_exit": 0',
    "restore": "restore_ready",
    "setup": "comfy_ready",
    "preflight": "PREFLIGHT_OK",
}
UPLOADS = (
    (CONFIG, "/content/rclone.conf"),
    (RESTORE / "colab-h3-rclone.gz", "/content/rclone.gz"),
    (REFERENCE, "/content/g4-c1-reference-graph.json"),
    (SCRIPTS / "h3_a100_ab_contract.py", "/content/h3_a100_ab_contract.py"),
    (SCRIPTS / "h3_a100_ab_child.py", "/content/h3_a100_ab_child.py"),
    (SCRIPTS / "h3_a100_ab_phase.py", "/content/h3_a100_ab_phase.py"),
    (SCRIPTS / "h3_a100_media.py", "/content/h3_a100_media.py"),
    (SCRIPTS / "h3_a100_phase_receipt.py", "/content/h3_a100_phase_receipt.py"),
    (SCRIPTS / "h3_g4_u02_child.py", "/content/h3_g4_u02_child.py"),
)


def local_preflight() -> tuple[Path, str]:
    required = [path for path, _ in UPLOADS] + [
        SCRIPTS / "colab_h3_restore.py", SCRIPTS / "colab_h3_preinstall_torch.py",
        SCRIPTS / "h3_a100_ab_preflight.py", SCRIPTS / "h3_g4_identity.py",
        SCRIPTS / "h3_g4_setup.py", SCRIPTS / "h3_g4_u02_phase.py",
        SCRIPTS / "colab_h3_paid_watchdog.sh",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing G4 trial inputs: {missing}")
    wheels = list(WHEEL_DIR.glob("sageattention-2.2.0-cp313-cp313-linux_x86_64.whl"))
    if len(wheels) != 1:
        raise RuntimeError("expected exactly one locally built cp313 SageAttention wheel")
    wheel = wheels[0]
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    graph = json.loads(REFERENCE.read_text())
    if graph.get("58", {}).get("class_type") != "MiniMaxH3MemoryEfficientSageAttentionPatch":
        raise RuntimeError("A100 C1 reference graph is not the Sage candidate")
    if graph.get("128", {}).get("inputs", {}).get("model") != ["58", 0]:
        raise RuntimeError("A100 C1 reference graph has no Sage model edge")
    archived = subprocess.run(
        ["tar", "-xOf", str(BACKUP / "colab-stage2-runner.tar"),
         "src/comfy_orch/gpu_adapt.py"], capture_output=True, check=True, timeout=30,
    ).stdout
    if hashlib.sha256(archived).hexdigest() != RESTORED_GPU_ADAPT_SHA256:
        raise RuntimeError("Drive runner archive no longer matches the G4 preflight hash")
    subprocess.run(["rclone", "about", "h3drive_h3:", "--config", str(CONFIG)],
                   check=True, timeout=30)
    return wheel, digest


def remote_json(path: str) -> dict:
    last_error = None
    for _ in range(3):
        try:
            result = subprocess.run(["rclone", "cat", path, "--config", str(CONFIG)],
                                    capture_output=True, check=True, timeout=30)
            return json.loads(result.stdout)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
                json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(2)
    raise RuntimeError(f"could not read verified Drive evidence: {path}: {last_error}")


def verify_preflight(remote: str) -> None:
    report = remote_json(f"{remote}/preflight.json")
    assets = report.get("assets", [])
    gpu_adapt = next((item for item in assets if item.get("path", "").endswith(
        "/src/comfy_orch/gpu_adapt.py")), None)
    if (len(assets) != 13 or not all(item.get("match") for item in assets)
            or not report.get("parent_match") or not gpu_adapt
            or gpu_adapt.get("sha256") != RESTORED_GPU_ADAPT_SHA256):
        raise RuntimeError("G4 frozen input preflight did not pass; do not submit U02")


def verify_phase(remote: str, session: str, log: Path) -> dict:
    marker = "G4_U02_PHASE_RESULT "
    lines = [line.partition(marker)[2] for line in log.read_text(errors="replace").splitlines()
             if marker in line]
    if len(lines) > 1:
        raise RuntimeError("multiple completed G4 phase results were captured")
    receipt = remote_json(f"{remote}/G4_U02/phase.json")
    if (receipt.get("state") != "success" or receipt.get("archive_state") != "verified"
            or receipt.get("session_id") != session or receipt.get("label") != "G4_U02"
            or receipt.get("input_manifest_sha256") != hashlib.sha256(
                subprocess.run(["rclone", "cat", f"{remote}/preflight.json", "--config", str(CONFIG)],
                               capture_output=True, check=True, timeout=30).stdout).hexdigest()):
        raise RuntimeError("G4 phase result and verified Drive receipt do not match")
    if lines and any(receipt.get(key) != value for key, value in json.loads(lines[0]).items()):
        raise RuntimeError("G4 phase log and verified Drive receipt do not match")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-paid", action="store_true")
    parser.add_argument("--safety-hours", type=float, default=4.0)
    args = parser.parse_args()
    if not 2 <= args.safety_hours <= 8:
        raise ValueError("safety deadline must be between two and eight hours")
    wheel, wheel_sha = local_preflight()
    session = "h3-g4-u02-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    remote = f"{REMOTE_BASE}/{session}"
    if not args.execute_paid:
        print(json.dumps({"ready": True, "paid_started": False, "wheel": str(wheel),
                          "wheel_sha256": wheel_sha, "reference_graph": str(REFERENCE),
                          "remote_prefix": remote}, indent=2))
        return
    logdir = BACKUP / "g4-u02" / session
    logdir.mkdir(parents=True, exist_ok=False)
    snapshots = logdir / "cu-snapshots.jsonl"
    before = snapshot(snapshots, "before_assignment")
    sessions = run(["colab", "sessions"], logdir / "sessions-before.log", timeout=30)
    if before["active"] or before["rate"] or "No active sessions" not in sessions:
        raise RuntimeError("Colab is not idle; no G4 assignment created")
    (logdir / "trial-inputs.json").write_text(json.dumps({
        "session": session, "remote": remote, "wheel_sha256": wheel_sha,
        "reference_graph_sha256": hashlib.sha256(REFERENCE.read_bytes()).hexdigest(),
        "safety_hours": args.safety_hours, "before": before,
    }, indent=2) + "\n")
    created = False
    watcher = None
    started = time.monotonic()
    deadline = datetime.now(timezone.utc) + timedelta(hours=args.safety_hours)
    try:
        created = True
        run(["colab", "new", "--session", session, "--gpu", "G4"],
            logdir / "assignment.log", timeout=180)
        assigned = snapshot(snapshots, "assigned")
        if assigned["active"] != 1 or assigned["rate"] <= 0:
            raise RuntimeError("G4 paid assignment was not confirmed")
        watcher_log = (logdir / "watchdog.log").open("w")
        try:
            watcher = subprocess.Popen(
                ["bash", str(SCRIPTS / "colab_h3_paid_watchdog.sh"),
                 session, deadline.isoformat()],
                stdin=subprocess.DEVNULL, stdout=watcher_log,
                stderr=subprocess.STDOUT, start_new_session=True,
            )
        finally:
            watcher_log.close()
        time.sleep(0.2)
        if watcher.poll() is not None:
            raise RuntimeError("paid-session watchdog exited before setup")
        print("G4_SESSION", session, "remote", remote, "deadline", deadline.isoformat(), flush=True)
        for source, destination in (*UPLOADS, (wheel, "/content/" + wheel.name)):
            run(["colab", "upload", "--session", session, str(source), destination],
                logdir / ("upload-" + source.name + ".log"), timeout=300)
        stages = (
            ("identity", SCRIPTS / "h3_g4_identity.py", 60, {}),
            ("preinstall", SCRIPTS / "colab_h3_preinstall_torch.py", 720, {}),
            ("restore", SCRIPTS / "colab_h3_restore.py", 2400, {}),
            ("setup", SCRIPTS / "h3_g4_setup.py", 900, {"H3_G4_WHEEL_SHA256": wheel_sha}),
            ("preflight", SCRIPTS / "h3_a100_ab_preflight.py", 600,
             {"H3_AB_PREFLIGHT_REMOTE": remote,
              "H3_GPU_ADAPT_EXPECTED_SHA256": RESTORED_GPU_ADAPT_SHA256}),
        )
        for name, path, timeout, env in stages:
            began = time.monotonic()
            exec_file(session, path, timeout, logdir / f"{name}.log", **env)
            if STAGE_MARKERS[name] not in (logdir / f"{name}.log").read_text(errors="replace"):
                raise RuntimeError(f"{name} stage had no success marker; stop without a prompt")
            if name == "preflight":
                verify_preflight(remote)
            state = snapshot(snapshots, name)
            (logdir / "stage-timing.jsonl").open("a").write(json.dumps({
                "stage": name, "elapsed_s": round(time.monotonic() - began, 2),
                "rate_cu_per_hour": state["rate"], "balance_cu": state["balance"],
            }) + "\n")
        began = time.monotonic()
        phase_log = logdir / "G4_U02.log"
        try:
            exec_file(session, SCRIPTS / "h3_g4_u02_phase.py", 4200,
                      phase_log, phase_label="G4_U02",
                      receipt_path=f"{remote}/G4_U02/phase.json",
                      H3_G4_REMOTE=remote)
        except (RuntimeError, TimeoutError):
            verify_phase(remote, session, phase_log)
        verify_phase(remote, session, phase_log)
        state = snapshot(snapshots, "after_G4_U02")
        (logdir / "stage-timing.jsonl").open("a").write(json.dumps({
            "stage": "G4_U02", "elapsed_s": round(time.monotonic() - began, 2),
            "rate_cu_per_hour": state["rate"], "balance_cu": state["balance"],
        }) + "\n")
        print("G4_U02_REMOTE", f"{remote}/G4_U02", flush=True)
    finally:
        if created:
            try:
                stop_and_verify(session, logdir, watcher)
            finally:
                try:
                    run(["colab", "log", "--session", session, "--output",
                         str(logdir / "colab-session.jsonl")], timeout=120)
                except (RuntimeError, TimeoutError) as exc:
                    print("SESSION_LOG_UNAVAILABLE", exc, flush=True)
                try:
                    run(["rclone", "copy", remote, str(logdir / "evidence"),
                         "--config", str(CONFIG), "--exclude", "*.mp4",
                         "--exclude", "*.safetensors"], timeout=300)
                except (RuntimeError, TimeoutError) as exc:
                    print("EVIDENCE_PULL_UNAVAILABLE", exc, flush=True)
                (logdir / "host-wall-s.txt").write_text(
                    f"{round(time.monotonic() - started, 2)}\n")


if __name__ == "__main__":
    main()
