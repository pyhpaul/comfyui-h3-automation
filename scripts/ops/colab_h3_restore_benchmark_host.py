"""One explicitly authorized G4 restore A/B, with CU and wall-time stop gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from colab_h3_a100_ab_host import CONFIG, SCRIPTS, run, snapshot, stop_and_verify
from colab_h3_restore_bootstrap_host import check_drive_bootstrap


ROOT = SCRIPTS.parents[1]
MANIFEST = ROOT / "docs/ops/drive-restore-rental-20260924-v1.json"
BOOTSTRAP_METADATA = ROOT / "docs/ops/drive-rclone-bootstrap-v1.json"
STOP_MARGIN_SECONDS = 120
STOP_MARGIN_CU = 0.4


def local_inputs() -> list[tuple[Path, str]]:
    uploads = [(CONFIG, "/content/rclone.conf"), (MANIFEST, "/content/restore-manifest.json"),
               (BOOTSTRAP_METADATA, "/content/rclone-bootstrap.json")]
    for name in ("colab_h3_restore.py", "colab_h3_restore_fast.py",
                 "colab_h3_restore_benchmark.py", "colab_h3_restore_bootstrap.py",
                 "h3_g4_identity.py"):
        uploads.append((SCRIPTS / name, f"/content/{name}"))
    required = [source for source, _ in uploads] + [SCRIPTS / "colab_h3_paid_watchdog.sh"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing restore benchmark inputs: {missing}")
    return uploads


def check_bootstrap() -> None:
    check_drive_bootstrap(CONFIG, BOOTSTRAP_METADATA, ROOT / "runs")


def work_seconds(started: float, now: float, *, rate: float, cap: float,
                 max_minutes: int) -> int:
    if rate <= 0:
        raise RuntimeError("invalid paid assignment rate")
    allowed = min(max_minutes * 60, (cap - STOP_MARGIN_CU) * 3600 / rate)
    remaining = math.floor(allowed - (now - started) - STOP_MARGIN_SECONDS)
    if remaining <= 0:
        raise RuntimeError("restore benchmark budget exhausted")
    return remaining


def verify_report(report: dict, session: str) -> None:
    runs = report.get("runs", [])
    if report.get("state") != "success" or report.get("session_id") != session or len(runs) != 2:
        raise RuntimeError("benchmark ended without an identity-bound success report")
    expected = [("baseline", 1), ("candidate", 4)]
    models = json.loads(MANIFEST.read_text())["models"]
    expected_models = {(m["relative_path"], m["bytes"], m["sha256"]) for m in models}
    for result, (label, workers) in zip(runs, expected):
        actual = {(m["relative_path"], m["bytes"], m["sha256"])
                  for m in result.get("models", [])}
        if (result.get("label") != label or result.get("workers") != workers
                or result.get("cold") is not True or result.get("verified_models") != 6
                or actual != expected_models
                or not 0 < result.get("model_seconds", 0) <= result.get("restore_seconds", 0)):
            raise RuntimeError("benchmark did not contain two fully verified cold restores")


def budget_poll(logdir: Path, before: dict, rate: float, started: float, args) -> None:
    try:
        state = snapshot(logdir / "cu-snapshots.jsonl", "budget_poll")
        work_seconds(started, time.monotonic(), rate=rate, cap=args.max_cu,
                     max_minutes=args.max_minutes)
    except (RuntimeError, OSError) as exc:
        raise TimeoutError("restore budget could not be verified; stop experiment") from exc
    estimate = rate * (time.monotonic() - started) / 3600
    observed = max(0.0, before["balance"] - state["balance"])
    if (state["active"] != 1 or state["rate"] > rate
            or max(estimate, observed) >= args.max_cu - STOP_MARGIN_CU):
        raise TimeoutError("CU/assignment gate failed; stop restore experiment")
    return None


def execute_remote(session: str, script: str, timeout: int, logdir: Path,
                   poll=None, **env: str) -> str:
    command = ["colab", "exec", "--session", session,
               "--file", str(SCRIPTS / script), "--timeout", str(timeout)]
    for key, value in env.items():
        command.extend(["--env", f"{key}={value}"])
    return run(command, logdir / (script + ".log"), timeout=timeout,
               detect_lost_connection=True, poll_receipt=poll, receipt_poll_interval=20)


def start_watchdog(session: str, deadline: datetime, logdir: Path) -> subprocess.Popen:
    with (logdir / "watchdog.log").open("w") as stream:
        watcher = subprocess.Popen(
            ["bash", str(SCRIPTS / "colab_h3_paid_watchdog.sh"), session, deadline.isoformat()],
            stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
            start_new_session=True)
    time.sleep(0.2)
    if watcher.poll() is not None:
        raise RuntimeError("restore watchdog did not remain alive")
    return watcher


def run_paid(args, uploads: list[tuple[Path, str]]) -> None:
    session = "h3-restore-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    logdir = ROOT / "runs" / session
    logdir.mkdir(exist_ok=False)
    before = snapshot(logdir / "cu-snapshots.jsonl", "before_assignment")
    sessions = run(["colab", "sessions"], logdir / "sessions-before.log", timeout=30)
    if (before["active"] or before["rate"] or before["balance"] < args.max_cu
            or "No active sessions" not in sessions):
        raise RuntimeError("restore benchmark requires an idle account and sufficient CU")
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
              for path, _ in uploads if path.name != "rclone.conf"}
    (logdir / "inputs.json").write_text(json.dumps({
        "session": session, "max_cu": args.max_cu, "max_minutes": args.max_minutes,
        "hashes": hashes, "before": before}, indent=2) + "\n")
    started = time.monotonic()
    created = False
    watcher = None
    try:
        created = True
        run(["colab", "new", "--session", session, "--gpu", "G4"],
            logdir / "assignment.log", timeout=180)
        # Start a conservative wall watchdog before doing any further setup.
        deadline = datetime.now(timezone.utc) + timedelta(
            seconds=max(1, args.max_minutes * 60 - (time.monotonic() - started) - 60))
        watcher = start_watchdog(session, deadline, logdir)
        assigned = snapshot(logdir / "cu-snapshots.jsonl", "assigned")
        if assigned["active"] != 1 or assigned["rate"] <= 0:
            raise RuntimeError("G4 paid assignment was not confirmed")
        rate = assigned["rate"]
        remaining = work_seconds(started, time.monotonic(), rate=rate, cap=args.max_cu,
                                 max_minutes=args.max_minutes)
        cu_deadline = datetime.now(timezone.utc) + timedelta(seconds=remaining + 60)
        if cu_deadline < deadline:
            replacement = start_watchdog(session, cu_deadline, logdir)
            watcher.terminate()
            watcher.wait(timeout=5)
            watcher = replacement
        poll = lambda: budget_poll(logdir, before, rate, started, args)
        print("RESTORE_BENCH_SESSION", session, "logs", logdir, flush=True)
        for source, destination in uploads:
            remaining = work_seconds(started, time.monotonic(), rate=rate, cap=args.max_cu,
                                     max_minutes=args.max_minutes)
            run(["colab", "upload", "--session", session, str(source), destination],
                logdir / ("upload-" + source.name + ".log"), timeout=min(60, remaining))
        identity = execute_remote(session, "h3_g4_identity.py", 60, logdir)
        if "G4_IDENTITY_OK" not in identity:
            raise RuntimeError("G4 identity did not pass; stop without restore")
        bootstrap = execute_remote(session, "colab_h3_restore_bootstrap.py", 120, logdir, poll=poll)
        if "RCLONE_BOOTSTRAP_OK" not in bootstrap:
            raise RuntimeError("frozen rclone bootstrap did not pass; stop without restore")
        poll()
        remaining = work_seconds(started, time.monotonic(), rate=rate, cap=args.max_cu,
                                 max_minutes=args.max_minutes)
        output = execute_remote(session, "colab_h3_restore_benchmark.py", remaining,
                                logdir, poll=poll, H3_RESTORE_BENCH_SESSION=session)
        lines = [line.split("RESTORE_BENCH_RESULT ", 1)[1] for line in output.splitlines()
                 if line.startswith("RESTORE_BENCH_RESULT ")]
        if len(lines) != 1:
            raise RuntimeError("restore ended without exactly one success marker")
        report = json.loads(lines[0])
        verify_report(report, session)
        for name, digest in report["script_hashes"].items():
            if hashes.get(name) != digest:
                raise RuntimeError(f"remote benchmark script hash mismatch: {name}")
        (logdir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print("RESTORE_BENCH_VERIFIED", json.dumps({"session": session,
              "saved_seconds": report["saved_seconds"], "saved_percent": report["saved_percent"],
              "speedup": report["speedup"]}), flush=True)
    finally:
        if created:
            stop_and_verify(session, logdir, watcher)
        (logdir / "host-wall.json").write_text(json.dumps({
            "seconds": time.monotonic() - started}) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-paid", action="store_true")
    parser.add_argument("--check-bootstrap", action="store_true")
    parser.add_argument("--max-cu", type=float, default=5)
    parser.add_argument("--max-minutes", type=int, default=30)
    args = parser.parse_args()
    if not 0.4 < args.max_cu <= 5 or not 3 <= args.max_minutes <= 30:
        raise ValueError("restore pilot is limited to 5 CU and 30 minutes")
    uploads = local_inputs()
    if args.check_bootstrap:
        if args.execute_paid:
            raise ValueError("bootstrap check cannot allocate a paid assignment")
        check_bootstrap()
        return
    if not args.execute_paid:
        print(json.dumps({"paid_started": False, "uploads": len(uploads),
                          "max_cu": args.max_cu, "max_minutes": args.max_minutes}))
        return
    check_bootstrap()
    run_paid(args, uploads)


if __name__ == "__main__":
    main()
