"""One restored A100 session for diagnostics and a conditional memory A/B.

This is a paid operator command, not an offline test. It requires explicit
--execute-paid and --max-cu flags; no assignment is created otherwise.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import time
from datetime import datetime, timedelta, timezone

from colab_h3_a100_ab_host import (BACKUP, CONFIG, SCRIPTS, admit_next, exec_file,
                                   run, snapshot, stop_and_verify)
from colab_h3_a100_profile_host import (REMOTE_ROOT, require_profile_files,
                                        restore_and_preflight, upload_controls)


PROFILE_LABELS = ("P_B", "P_C", "M0")
FORMAL_LABELS = ("S1", "M1", "S2", "M2")
MAX_CU = 20.0
MAX_RESERVED_BYTES = 70 * 1024 ** 3


def require_combined_inputs() -> None:
    require_profile_files()
    for name in ("comfy_gpu_start.sh", "colab_h3_a100_combined_host.py"):
        path = SCRIPTS / name
        if not path.is_file():
            raise RuntimeError(f"missing combined-pilot input: {path}")
    subprocess.run(["bash", "-n", str(SCRIPTS / "comfy_gpu_start.sh")],
                   check=True, timeout=10)


def run_checked_phase(session: str, label: str, remote: str, logdir,
                      snapshots, before: dict[str, float], started: float,
                      cap: float, deadline: datetime, assigned_rate: float) -> None:
    state = snapshot(snapshots, f"before_{label}")
    if state["rate"] > assigned_rate + 0.01:
        raise RuntimeError("Colab CU rate increased; stop under the original deadline")
    profile = label in PROFILE_LABELS
    planned_seconds = 1350 if profile else 2700
    admit_next(state, before["balance"], started, cap, deadline, planned_seconds)
    if profile:
        path = SCRIPTS / "h3_a100_profile_phase.py"
        environment = {"H3_PROFILE_REMOTE": remote, "H3_PROFILE_LABEL": label,
                       "H3_COMFY_START_SCRIPT": "/content/h3_a100_memory_start.sh",
                       "H3_DISABLE_SMART_MEMORY": "0" if label == "M0" else "1"}
        timeout = 1200
    else:
        path = SCRIPTS / "h3_a100_ab_phase.py"
        environment = {"H3_AB_REMOTE": remote, "H3_AB_RUN": label}
        timeout = 2600
    exec_file(session, path, timeout, logdir / f"{label}.log", phase_label=label,
              receipt_path=f"{remote}/{label}/phase.json", **environment)
    snapshot(snapshots, f"after_{label}")


def check_memory_profile(remote: str) -> dict:
    result = subprocess.run(["rclone", "cat", f"{remote}/M0/sampler-profile.json",
                             "--config", str(CONFIG)], capture_output=True, text=True,
                            check=True, timeout=60)
    report = json.loads(result.stdout)
    if report.get("kind") != "instrumented_one_step_not_timing_sample":
        raise RuntimeError("M0 profiler report has the wrong experiment kind")
    if "A100-SXM4-80GB" not in report.get("gpu", ""):
        raise RuntimeError("M0 profiler did not observe the planned A100")
    if not 0 < report["peak_reserved_bytes"] <= MAX_RESERVED_BYTES:
        raise RuntimeError("M0 profiler exceeded the 70 GiB safety gate")
    return report


def check_profile_startup_contract(remote: str) -> None:
    receipts = []
    for label in PROFILE_LABELS:
        result = subprocess.run(["rclone", "cat", f"{remote}/{label}/phase.json",
                                 "--config", str(CONFIG)], capture_output=True, text=True,
                                check=True, timeout=60)
        receipt = json.loads(result.stdout)
        if receipt.get("label") != label or receipt.get("state") != "success":
            raise RuntimeError(f"{label} profiler phase receipt is invalid")
        receipts.append(receipt)
    hashes = {item.get("startup_sha256") for item in receipts}
    if (len(hashes) != 1 or None in hashes
            or [item.get("disable_smart_memory") for item in receipts] != ["1", "1", "0"]):
        raise RuntimeError("diagnostic startup differs beyond the memory flag")


def execute_assigned_batch(session: str, remote: str, logdir, snapshots,
                           before: dict[str, float], started: float,
                           cap: float, deadline: datetime, assigned_rate: float) -> None:
    upload_controls(session)
    run(["colab", "upload", "--session", session,
         str(SCRIPTS / "comfy_gpu_start.sh"), "/content/h3_a100_memory_start.sh"],
        timeout=180)
    restore_and_preflight(session, logdir, snapshots, assigned_rate, remote)
    for label in PROFILE_LABELS:
        run_checked_phase(session, label, remote, logdir, snapshots, before,
                          started, cap, deadline, assigned_rate)
    check_profile_startup_contract(remote)
    report = check_memory_profile(remote)
    (logdir / "M0-safety.json").write_text(json.dumps({
        "gpu": report["gpu"], "peak_reserved_bytes": report["peak_reserved_bytes"],
        "max_allowed_bytes": MAX_RESERVED_BYTES}, indent=2) + "\n")
    for label in FORMAL_LABELS:
        run_checked_phase(session, label, remote, logdir, snapshots, before,
                          started, cap, deadline, assigned_rate)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-paid", action="store_true")
    parser.add_argument("--max-cu", required=True, type=float)
    args = parser.parse_args()
    if not args.execute_paid or not 0 < args.max_cu <= MAX_CU:
        raise ValueError("explicit --execute-paid and a CU cap in (0, 20] are required")
    require_combined_inputs()
    session = "h3-a100-combined-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    remote = f"{REMOTE_ROOT}/profile-{session}"
    logdir = BACKUP / "a100-perf-pilot" / session
    logdir.mkdir(parents=True, exist_ok=False)
    snapshots = logdir / "cu-snapshots.jsonl"
    before = snapshot(snapshots, "before_assignment")
    if before["active"] or before["rate"] or before["balance"] < args.max_cu:
        raise RuntimeError("pre-assignment balance or idle-state gate failed")
    started = time.monotonic()
    created = False
    watcher = None
    try:
        created = True
        run(["colab", "new", "--session", session, "--gpu", "A100", "--high-mem"],
            logdir / "assignment.log", timeout=180)
        assigned = snapshot(snapshots, "assigned")
        if assigned["active"] != 1 or assigned["rate"] <= 0:
            raise RuntimeError("Colab assignment rate could not be confirmed")
        maximum_seconds = math.floor((args.max_cu - 1.0) / assigned["rate"] * 3600)
        deadline = datetime.now(timezone.utc) + timedelta(
            seconds=maximum_seconds - (time.monotonic() - started))
        if maximum_seconds < 3600 or deadline <= datetime.now(timezone.utc) + timedelta(hours=1):
            raise RuntimeError("insufficient combined-pilot CU window")
        with (logdir / "watchdog.log").open("w") as stream:
            watcher = subprocess.Popen(["bash", str(SCRIPTS / "colab_h3_paid_watchdog.sh"),
                                        session, deadline.isoformat()],
                                       stdin=subprocess.DEVNULL, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
        time.sleep(0.2)
        if watcher.poll() is not None:
            raise RuntimeError("paid-session watchdog exited early")
        print("COMBINED_SESSION", session, "deadline", deadline.isoformat(), flush=True)
        execute_assigned_batch(session, remote, logdir, snapshots, before, started,
                               args.max_cu, deadline, assigned["rate"])
    finally:
        if created:
            stop_and_verify(session, logdir, watcher)
            run(["colab", "log", "--session", session, "--output",
                 str(logdir / "colab-session.jsonl")], timeout=120)
            run(["rclone", "copy", remote, str(logdir / "evidence"), "--config",
                 str(CONFIG), "--exclude", "*.mp4", "--exclude", "*.safetensors"],
                timeout=300)


if __name__ == "__main__":
    main()
