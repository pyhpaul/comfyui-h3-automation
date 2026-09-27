"""One-session A100 U02 bypass-vs-Sage pilot with a hard CU/deadline gate.

This script is deliberately not run by tests: invoking it creates a paid
Colab GPU assignment. It requires an explicit operator command.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import signal
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from h3_a100_phase_receipt import ReceiptIdentity, receipt_status


ROOT = Path(__file__).resolve().parents[2]
BACKUP = Path("/mnt/d/comfyui-h3-backups/rental-20260924-5090")
SCRIPTS = ROOT / "scripts/ops"
CONTROL = BACKUP / "a100-perf-pilot/control-scripts"
RESTORE = BACKUP / "colab-stage2/control-scripts"
REMOTE = "h3drive_h3:comfyui-h3-colab-dedicated/rental-20260924-5090/a100-perf-pilot/formal-ab-1"
CONFIG = Path.home() / ".config/rclone-h3/rclone.conf"
USAGE_RE = re.compile(r"^(Current balance|Usage rate|Active assignments):\s*([\d.]+)", re.M)
LOST_CONNECTION = "RuntimeError: Connection was lost."


class ColabTransportLost(RuntimeError):
    pass


class PhaseReceiptTerminal(RuntimeError):
    def __init__(self, state: str):
        super().__init__(f"verified remote phase receipt: {state}")
        self.state = state


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def terminate_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        kill_group(process)
        process.wait(timeout=5)


def kill_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run(command: list[str], log: Path | None = None, timeout: int = 300,
        detect_lost_connection: bool = False,
        poll_receipt: Callable[[], str | None] | None = None,
        receipt_poll_interval: float = 10.0) -> str:
    output: list[str] = []
    lost = threading.Event()
    stream = log.open("w") if log else None
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, bufsize=1, start_new_session=True)
    assert process.stdout is not None

    def consume() -> None:
        for line in process.stdout:
            output.append(line)
            print(line, end="", flush=True)
            if stream:
                stream.write(line)
                stream.flush()
            if detect_lost_connection and LOST_CONNECTION in line:
                lost.set()

    reader = threading.Thread(target=consume, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout
    next_receipt_poll = time.monotonic() + receipt_poll_interval
    try:
        while process.poll() is None:
            if lost.is_set():
                raise ColabTransportLost(f"Colab transport lost: {command[:3]}")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"host command exceeded {timeout}s: {command[:3]}")
            if poll_receipt is not None and time.monotonic() >= next_receipt_poll:
                state = poll_receipt()
                next_receipt_poll = time.monotonic() + receipt_poll_interval
                if state in {"success", "failed"}:
                    raise PhaseReceiptTerminal(state)
            try:
                process.wait(timeout=min(1, remaining))
            except subprocess.TimeoutExpired:
                continue
        reader.join(timeout=2)
        if reader.is_alive():
            terminate_group(process)
            reader.join(timeout=2)
        if reader.is_alive():
            kill_group(process)
            reader.join(timeout=2)
        if lost.is_set():
            raise ColabTransportLost(f"Colab transport lost: {command[:3]}")
        if reader.is_alive():
            raise RuntimeError(f"command output pipe did not close: {command[:3]}")
        if process.returncode:
            raise RuntimeError(f"command exited {process.returncode}: {command[:3]}")
        return "".join(output)
    except (ColabTransportLost, TimeoutError, PhaseReceiptTerminal):
        terminate_group(process)
        reader.join(timeout=2)
        if reader.is_alive():
            kill_group(process)
            reader.join(timeout=2)
        raise
    finally:
        if stream:
            stream.close()


def remaining_timeout(stage_end: float | None, requested: float) -> float:
    if stage_end is None:
        return requested
    remaining = stage_end - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("A100 diagnostic stage deadline elapsed")
    return min(requested, remaining)


def usage(stage_end: float | None = None) -> dict[str, float]:
    values = dict(USAGE_RE.findall(run(
        ["colab", "usage"], timeout=remaining_timeout(stage_end, 30))))
    if set(values) != {"Current balance", "Usage rate", "Active assignments"}:
        raise RuntimeError(f"could not parse Colab usage: {values}")
    return {"balance": float(values["Current balance"]),
            "rate": float(values["Usage rate"]),
            "active": float(values["Active assignments"])}


def snapshot(path: Path, label: str, stage_end: float | None = None) -> dict[str, float]:
    state = usage(stage_end)
    with path.open("a") as stream:
        stream.write(json.dumps({"at_utc": utc_now(), "label": label, **state}) + "\n")
    return state


def check_local_inputs() -> None:
    required = [CONFIG, RESTORE / "colab-h3-rclone.gz", RESTORE / "colab_h3_restore.py",
                CONTROL / "h3_a100_identity.py", CONTROL / "h3_a100_preinstall_torch.py",
                CONTROL / "h3_gpu_wheel_pull.py", CONTROL / "h3_a100_setup.py",
                SCRIPTS / "h3_a100_ab_contract.py", SCRIPTS / "h3_a100_ab_child.py",
                SCRIPTS / "h3_a100_media.py", SCRIPTS / "h3_a100_phase_receipt.py",
                SCRIPTS / "h3_a100_ab_preflight.py", SCRIPTS / "h3_a100_ab_phase.py",
                SCRIPTS / "colab_h3_paid_watchdog.sh"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing local A/B inputs: {missing}")


def phase_receipt_status(receipt: dict, label: str, attempted_at: datetime) -> str:
    if receipt.get("label") != label:
        return "wrong_label"
    try:
        started_at = datetime.fromisoformat(receipt["started_at_utc"])
    except (KeyError, TypeError, ValueError):
        return "invalid_timestamp"
    if started_at.tzinfo is None or started_at < attempted_at:
        return "stale"
    return str(receipt.get("state", "unknown"))


def remote_manifest_sha256(receipt_path: str, stage_end: float | None = None) -> str:
    remote = receipt_path.rsplit("/", 2)[0] + "/preflight.json"
    result = subprocess.run(["rclone", "cat", remote, "--config", str(CONFIG)],
                            capture_output=True, check=True,
                            timeout=remaining_timeout(stage_end, 15))
    return hashlib.sha256(result.stdout).hexdigest()


def verified_remote_state(receipt_path: str, identity: ReceiptIdentity,
                          attempted_at: datetime,
                          stage_end: float | None = None) -> str | None:
    try:
        result = subprocess.run(["rclone", "cat", receipt_path, "--config", str(CONFIG)],
                                capture_output=True, check=False,
                                timeout=remaining_timeout(stage_end, 5))
        if result.returncode:
            return None
        state = receipt_status(json.loads(result.stdout), identity, attempted_at)
        return state if state in {"success", "failed"} else None
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, TimeoutError):
        return None


def reconcile_phase(label: str, attempted_at: datetime, log: Path,
                    receipt_path: str | None = None,
                    identity: ReceiptIdentity | None = None,
                    stage_end: float | None = None) -> None:
    remote = receipt_path or f"{REMOTE}/{label}/phase.json"
    report: dict[str, object] = {"label": label, "attempted_at_utc": attempted_at.isoformat(),
                                 "action": "stop_without_retry"}
    try:
        result = subprocess.run(["rclone", "cat", remote, "--config", str(CONFIG)],
                               capture_output=True, text=True,
                               timeout=remaining_timeout(stage_end, 5), check=False)
        if result.returncode:
            report["receipt_status"] = "missing_or_unavailable"
        else:
            receipt = json.loads(result.stdout)
            report["receipt_status"] = (receipt_status(receipt, identity, attempted_at)
                                        if identity is not None else
                                        phase_receipt_status(receipt, label, attempted_at))
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, TimeoutError) as exc:
        report["receipt_status"] = "unavailable"
        report["receipt_error"] = type(exc).__name__
    try:
        report["usage"] = usage(stage_end)
    except (RuntimeError, TimeoutError, OSError) as exc:
        report["usage_error"] = type(exc).__name__
    log.with_suffix(".reconcile.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PHASE_RECONCILED_STOP_NO_RETRY", json.dumps(report), flush=True)


def exec_file(session: str, path: Path, timeout: int, log: Path,
              phase_label: str | None = None, receipt_path: str | None = None,
              input_manifest_sha256: str | None = None,
              host_timeout: int | None = None,
              stage_end: float | None = None,
              **environ: str) -> None:
    if phase_label and not receipt_path:
        raise ValueError("phase receipt path is required")
    attempted_at = datetime.now(timezone.utc)
    identity = None
    if phase_label and receipt_path:
        manifest = input_manifest_sha256 or remote_manifest_sha256(receipt_path, stage_end)
        identity = ReceiptIdentity(session, phase_label, uuid.uuid4().hex, manifest)
        environ.update({"H3_SESSION_ID": session, "H3_ATTEMPT_ID": identity.attempt_id,
                        "H3_INPUT_MANIFEST_SHA256": manifest})
    command = ["colab", "exec", "--session", session, "--file", str(path),
               "--timeout", str(timeout)]
    for key, value in environ.items():
        command += ["--env", f"{key}={value}"]
    try:
        poll = (lambda: verified_remote_state(receipt_path, identity, attempted_at, stage_end)
                if receipt_path and identity else None)
        run(command, log, timeout=remaining_timeout(
            stage_end, min(timeout + 120, host_timeout or timeout + 120)),
            detect_lost_connection=True,
            poll_receipt=poll if identity else None)
        if identity and receipt_path:
            state = verified_remote_state(receipt_path, identity, attempted_at, stage_end)
            if state != "success":
                raise RuntimeError(f"phase ended without verified success receipt: {state}")
    except PhaseReceiptTerminal as terminal:
        if terminal.state == "success":
            return
        if phase_label:
            reconcile_phase(phase_label, attempted_at, log, receipt_path, identity, stage_end)
        raise RuntimeError(f"verified remote phase failed: {phase_label}") from terminal
    except (RuntimeError, TimeoutError):
        state = (verified_remote_state(receipt_path, identity, attempted_at, stage_end)
                 if receipt_path and identity else None)
        if phase_label:
            reconcile_phase(phase_label, attempted_at, log, receipt_path, identity, stage_end)
        if state == "success":
            return
        raise


def admit_next(state: dict[str, float], starting_balance: float, started: float,
               cap: float, deadline: datetime, planned_seconds: int) -> None:
    rate = state["rate"]
    if state["active"] != 1 or rate <= 0:
        raise RuntimeError("A100 assignment is not active")
    elapsed_charge = rate * (time.monotonic() - started) / 3600
    observed_charge = max(0.0, starting_balance - state["balance"])
    remaining = cap - max(elapsed_charge, observed_charge)
    required = rate * planned_seconds / 3600 + 1.0
    if required > remaining or datetime.now(timezone.utc) + timedelta(seconds=planned_seconds) > deadline:
        raise RuntimeError(f"CU/deadline gate rejected next run: required={required:.2f}, remaining={remaining:.2f}")


def stop_and_verify(session: str, logdir: Path, watcher: subprocess.Popen | None) -> None:
    try:
        run(["colab", "stop", "--session", session], logdir / "stop.log", timeout=90)
    except (RuntimeError, TimeoutError) as exc:
        print(f"STOP_RETRY_NEEDED {exc}", flush=True)
    state = snapshot(logdir / "cu-snapshots.jsonl", "after_stop")
    sessions = run(["colab", "sessions"], logdir / "sessions-after-stop.log", timeout=30)
    if state["active"] != 0 or state["rate"] != 0 or "No active sessions" not in sessions:
        raise RuntimeError("Colab did not confirm zero active paid assignments")
    if watcher and watcher.poll() is None:
        watcher.terminate()
        try:
            watcher.wait(timeout=5)
        except subprocess.TimeoutExpired:
            watcher.kill()
            watcher.wait(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-cu", type=float, default=20.0)
    args = parser.parse_args()
    if not 0 < args.max_cu <= 20:
        raise ValueError("formal A/B CU cap must be in (0, 20]")
    check_local_inputs()
    session = "h3-a100-ab-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
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
            logdir / "assignment.log")
        assigned = snapshot(snapshots, "assigned")
        if assigned["active"] != 1 or assigned["rate"] <= 0:
            raise RuntimeError("Colab assignment rate could not be confirmed")
        maximum_seconds = math.floor((args.max_cu - 1.0) / assigned["rate"] * 3600)
        deadline = datetime.now(timezone.utc) + timedelta(seconds=maximum_seconds - (time.monotonic() - started))
        if maximum_seconds < 7200 or deadline <= datetime.now(timezone.utc) + timedelta(minutes=30):
            raise RuntimeError("insufficient formal-stage CU window for a one-session pilot")
        with (logdir / "watchdog.log").open("w") as stream:
            watcher = subprocess.Popen(["bash", str(SCRIPTS / "colab_h3_paid_watchdog.sh"),
                                        session, deadline.isoformat()],
                                       stdin=subprocess.DEVNULL, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
        time.sleep(0.2)
        if watcher.poll() is not None:
            raise RuntimeError("paid-session watchdog exited before the first phase")
        print("AB_SESSION", session, "deadline", deadline.isoformat(), flush=True)

        for source, destination in ((CONFIG, "/content/rclone.conf"),
                                    (RESTORE / "colab-h3-rclone.gz", "/content/rclone.gz"),
                                    (SCRIPTS / "h3_a100_ab_contract.py", "/content/h3_a100_ab_contract.py"),
                                    (SCRIPTS / "h3_a100_ab_child.py", "/content/h3_a100_ab_child.py"),
                                    (SCRIPTS / "h3_a100_media.py", "/content/h3_a100_media.py"),
                                    (SCRIPTS / "h3_a100_phase_receipt.py", "/content/h3_a100_phase_receipt.py")):
            run(["colab", "upload", "--session", session, str(source), destination])
        stages = [
            ("identity", CONTROL / "h3_a100_identity.py", 60),
            ("preinstall", CONTROL / "h3_a100_preinstall_torch.py", 180),
            ("restore", RESTORE / "colab_h3_restore.py", 1200),
            ("wheel_pull", CONTROL / "h3_gpu_wheel_pull.py", 180),
            ("setup", CONTROL / "h3_a100_setup.py", 180),
            ("preflight", SCRIPTS / "h3_a100_ab_preflight.py", 600),
        ]
        for name, path, timeout in stages:
            exec_file(session, path, timeout, logdir / f"{name}.log")
            state = snapshot(snapshots, name)
            if state["rate"] > assigned["rate"] + 0.01:
                raise RuntimeError("Colab CU rate increased; original watchdog deadline is no longer safe")
        for label in ("P_B", "P_C", "B1", "C1", "B2", "C2"):
            state = snapshot(snapshots, f"before_{label}")
            if state["rate"] > assigned["rate"] + 0.01:
                raise RuntimeError("Colab CU rate increased; stop and re-admit the batch")
            admit_next(state, before["balance"], started, args.max_cu, deadline,
                       2400 if label.startswith(("B", "C")) else 600)
            exec_file(session, SCRIPTS / "h3_a100_ab_phase.py", 2600,
                      logdir / f"{label}.log", phase_label=label, H3_AB_RUN=label)
            snapshot(snapshots, f"after_{label}")
    finally:
        if created:
            stop_and_verify(session, logdir, watcher)
            run(["colab", "log", "--session", session, "--output",
                 str(logdir / "colab-session.jsonl")], timeout=120)
            run(["rclone", "copy", REMOTE, str(logdir / "evidence"), "--config", str(CONFIG),
                 "--exclude", "*.mp4", "--exclude", "*.safetensors"], timeout=300)


if __name__ == "__main__":
    main()
