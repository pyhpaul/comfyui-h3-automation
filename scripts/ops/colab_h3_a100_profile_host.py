"""Bounded A100 one-step profiler driver; requires separate paid authorization.

Do not run this during offline preparation. The profiler result is diagnostic,
not a comparable U02 timing sample or a quality gate.
"""

from __future__ import annotations

import argparse
import math
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from colab_h3_a100_ab_host import (BACKUP, CONFIG, CONTROL, RESTORE, SCRIPTS,
                                   admit_next, check_local_inputs, exec_file,
                                   run, snapshot, stop_and_verify)
from h3_a100_profile_hook import EXPECTED_SHA256, digest
from h3_a100_attention_probe_hook import EXPECTED_SHA256 as ATTENTION_SHA256


REMOTE_ROOT = ("h3drive_h3:comfyui-h3-colab-dedicated/rental-20260924-5090/"
               "a100-perf-pilot")
PROFILE_FILES = ("h3_a100_profile_hook.py", "h3_a100_profile_runtime.py",
                 "h3_a100_trace_analysis.py",
                 "h3_a100_profile_phase.py", "h3_a100_attention_probe_hook.py",
                 "h3_a100_attention_probe.py")
SETUP_SECONDS = 22 * 60
PROFILE_AND_ARCHIVE_SECONDS = 9 * 60
STOP_SECONDS = 4 * 60
STAGE_ENVELOPE_SECONDS = SETUP_SECONDS + PROFILE_AND_ARCHIVE_SECONDS + STOP_SECONDS
PLANNING_RATE_CU_PER_HOUR = 7.5
PROFILE_GATE1_ENABLED = False  # FunctionEvent cannot establish a nonzero causal lower bound.


def bounded_timeout(stage_end: float | None, deadline: datetime | None,
                    requested: int) -> int:
    if stage_end is None or deadline is None:
        return requested
    available = min(stage_end - time.monotonic(),
                    (deadline - datetime.now(timezone.utc)).total_seconds())
    if available < 1:
        raise TimeoutError("A100 diagnostic stage deadline elapsed")
    return min(requested, math.floor(available))


def require_profile_files() -> None:
    check_local_inputs()
    missing = [name for name in PROFILE_FILES if not (SCRIPTS / name).is_file()]
    if missing:
        raise RuntimeError(f"missing profiler control files: {missing}")
    archive = BACKUP / "source-only.tar"
    source = subprocess.run(["tar", "-xOf", str(archive),
                             "./ComfyUI/comfy_extras/nodes_custom_sampler.py"],
                            capture_output=True, check=True, timeout=30)
    if digest(source.stdout) != EXPECTED_SHA256:
        raise RuntimeError("local archived ComfyUI sampler hash differs from profiler hook")
    attention = subprocess.run(["tar", "-xOf", str(archive),
                                "./ComfyUI/custom_nodes/ComfyUI-KJNodes/nodes/ltxv_nodes.py"],
                               capture_output=True, check=True, timeout=30)
    if digest(attention.stdout) != ATTENTION_SHA256:
        raise RuntimeError("local archived KJNodes hash differs from attention probe hook")


def upload_controls(session: str, stage_end: float | None = None,
                    deadline: datetime | None = None) -> None:
    controls = ((CONFIG, "/content/rclone.conf"),
                (RESTORE / "colab-h3-rclone.gz", "/content/rclone.gz"),
                *((SCRIPTS / name, f"/content/{name}") for name in
                  ("h3_a100_ab_contract.py", "h3_a100_ab_child.py", "h3_a100_ab_phase.py",
                   "h3_a100_media.py", "h3_a100_phase_receipt.py", *PROFILE_FILES)))
    for source, destination in controls:
        run(["colab", "upload", "--session", session, str(source), destination],
            timeout=bounded_timeout(stage_end, deadline, 180))


def restore_and_preflight(session: str, logdir: Path, snapshots: Path,
                          assigned_rate: float, remote: str,
                          stage_end: float | None = None,
                          deadline: datetime | None = None) -> None:
    stages = (("identity", CONTROL / "h3_a100_identity.py", 60),
              ("preinstall", CONTROL / "h3_a100_preinstall_torch.py", 180),
              ("restore", RESTORE / "colab_h3_restore.py", 1200),
              ("wheel_pull", CONTROL / "h3_gpu_wheel_pull.py", 180),
              ("setup", CONTROL / "h3_a100_setup.py", 180),
              ("preflight", SCRIPTS / "h3_a100_ab_preflight.py", 600))
    for name, path, timeout in stages:
        environment = {"H3_AB_PREFLIGHT_REMOTE": remote} if name == "preflight" else {}
        exec_file(session, path, timeout, logdir / f"{name}.log",
                  host_timeout=bounded_timeout(stage_end, deadline, timeout + 120),
                  stage_end=stage_end,
                  **environment)
        state = snapshot(snapshots, name, stage_end)
        if state["rate"] > assigned_rate + 0.01:
            raise RuntimeError("Colab CU rate increased; stop under the original deadline")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-paid", action="store_true")
    parser.add_argument("--attended", action="store_true")
    parser.add_argument("--max-cu", required=True, type=float)
    args = parser.parse_args()
    if not args.execute_paid or not args.attended or not 0 < args.max_cu <= 6:
        raise ValueError("explicit --execute-paid, --attended and a CU cap in (0, 6] are required")
    if not PROFILE_GATE1_ENABLED:
        raise RuntimeError("Gate 1 is disabled pending a reviewed causal probe design")
    require_profile_files()
    session = "h3-a100-profile-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    remote = f"{REMOTE_ROOT}/profile-{session}"
    logdir = BACKUP / "a100-perf-pilot" / session
    logdir.mkdir(parents=True, exist_ok=False)
    snapshots = logdir / "cu-snapshots.jsonl"
    before = snapshot(snapshots, "before_assignment")
    if before["active"] or before["rate"] or before["balance"] < args.max_cu:
        raise RuntimeError("pre-assignment balance or idle-state gate failed")
    if ((args.max_cu - 1.0) / PLANNING_RATE_CU_PER_HOUR * 3600
            < STAGE_ENVELOPE_SECONDS):
        raise RuntimeError("6 CU planning-rate scenario cannot fit the diagnostic stage envelope")
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
        if (maximum_seconds < STAGE_ENVELOPE_SECONDS
                or deadline <= datetime.now(timezone.utc)
                + timedelta(seconds=STAGE_ENVELOPE_SECONDS)):
            raise RuntimeError("insufficient profiler CU window")
        with (logdir / "watchdog.log").open("w") as stream:
            watcher = subprocess.Popen(["bash", str(SCRIPTS / "colab_h3_paid_watchdog.sh"),
                                        session, deadline.isoformat()],
                                       stdin=subprocess.DEVNULL, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
        time.sleep(0.2)
        if watcher.poll() is not None:
            raise RuntimeError("paid-session watchdog exited early")
        print("PROFILE_SESSION", session, "deadline", deadline.isoformat(), flush=True)
        setup_end = time.monotonic() + SETUP_SECONDS
        upload_controls(session, setup_end, deadline)
        restore_and_preflight(session, logdir, snapshots, assigned["rate"], remote,
                              setup_end, deadline)
        bounded_timeout(setup_end, deadline, 1)
        state = snapshot(snapshots, "before_profile", setup_end)
        admit_next(state, before["balance"], started, args.max_cu, deadline,
                   PROFILE_AND_ARCHIVE_SECONDS + STOP_SECONDS)
        profile_end = time.monotonic() + PROFILE_AND_ARCHIVE_SECONDS
        exec_file(session, SCRIPTS / "h3_a100_profile_phase.py",
                  bounded_timeout(profile_end, deadline, PROFILE_AND_ARCHIVE_SECONDS),
                  logdir / "profile.log", phase_label="P_C",
                  receipt_path=f"{remote}/P_C/phase.json", H3_PROFILE_REMOTE=remote,
                  H3_PROFILE_LABEL="P_C", H3_ATTENTION_CAPTURE="0",
                  host_timeout=bounded_timeout(profile_end, deadline,
                                               PROFILE_AND_ARCHIVE_SECONDS),
                  stage_end=profile_end)
        snapshot(snapshots, "after_profile", profile_end)
    finally:
        if created:
            stop_and_verify(session, logdir, watcher)
            run(["colab", "log", "--session", session, "--output",
                 str(logdir / "colab-session.jsonl")], timeout=120)
            run(["rclone", "copy", remote, str(logdir / "evidence"), "--config",
                 str(CONFIG), "--exclude", "*.safetensors"], timeout=300)


if __name__ == "__main__":
    main()
