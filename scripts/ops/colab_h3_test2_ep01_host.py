"""Supervised G4 production of Test2 EP01 with per-unit receipts and review gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from colab_h3_a100_ab_host import admit_next, exec_file, run, snapshot, stop_and_verify
from colab_h3_g4_u02_host import (
    BACKUP, CONFIG, SCRIPTS, UPLOADS, STAGE_MARKERS, RESTORED_GPU_ADAPT_SHA256,
    local_preflight, remote_json, verify_preflight,
)
from h3_test2_ep01_contract import PARENTS, UNITS
from h3_test2_ep01_inputs import archive_members


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/ops/drive-test2-ep01-v1.json"
LOCAL_ARCHIVE = BACKUP / "test2-ep01/inputs/test2-ep01-jobs-v1.tar"
REMOTE_ROOT = "h3drive_h3:comfyui-h3-colab-dedicated/standard-v1/runs/test2-20260925/ep01"
EXTRA_UPLOADS = (
    (MANIFEST, "/content/test2-ep01-input-manifest.json"),
    (SCRIPTS / "h3_g4_u02_phase.py", "/content/h3_g4_u02_phase.py"),
    (SCRIPTS / "h3_test2_ep01_contract.py", "/content/h3_test2_ep01_contract.py"),
    (SCRIPTS / "h3_test2_ep01_media.py", "/content/h3_test2_ep01_media.py"),
    (SCRIPTS / "h3_test2_ep01_child.py", "/content/h3_test2_ep01_child.py"),
)
REVIEW_UNITS = frozenset({"U01", "U04", "U05"})


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def remote_file_matches(record: dict) -> bool:
    result = subprocess.run(
        ["rclone", "lsjson", record["remote"], "--stat", "--hash",
         "--config", str(CONFIG)],
        capture_output=True, check=True, timeout=40,
    )
    remote = json.loads(result.stdout)
    return (
        remote.get("Size") == record["bytes"]
        and remote.get("Hashes", {}).get("sha256") == record["sha256"]
    )


def local_inputs() -> tuple[Path, str, dict]:
    wheel, wheel_sha = local_preflight()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    archive = manifest["job_archive"]
    if (
        manifest.get("schema_version") != 1
        or manifest.get("units") != list(UNITS)
        or manifest.get("independent_starts") != ["U01", "U05"]
        or not LOCAL_ARCHIVE.is_file()
        or LOCAL_ARCHIVE.stat().st_size != archive["bytes"]
        or sha256(LOCAL_ARCHIVE) != archive["sha256"]
        or not remote_file_matches(archive)
    ):
        raise RuntimeError("local or Drive Test2 inputs differ from frozen manifest")
    archive_members(LOCAL_ARCHIVE)
    required = [path for path, _ in EXTRA_UPLOADS]
    required.extend(SCRIPTS / name for name in (
        "h3_test2_ep01_inputs.py", "h3_test2_ep01_phase.py",
        "h3_a100_ab_contract.py", "h3_a100_ab_phase.py",
        "h3_a100_phase_receipt.py", "h3_g4_u02_phase.py",
        "colab_h3_paid_watchdog.sh",
    ))
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing Test2 G4 scripts: {missing}")
    return wheel, wheel_sha, manifest


def verify_inputs(remote: str, manifest: dict) -> None:
    report = remote_json(f"{remote}/inputs.json")
    if (
        report.get("state") != "ready"
        or report.get("units") != list(UNITS)
        or report.get("archive_sha256") != manifest["job_archive"]["sha256"]
        or report.get("source_zip_sha256") != manifest["source_zip_sha256"]
    ):
        raise RuntimeError("remote Test2 input admission failed")


def unit_remote(session_remote: str, unit: str) -> str:
    return f"{session_remote}/{unit.lower()}"


def verify_unit(remote: str, session: str, unit: str,
                parent: str | None, manifest_sha: str) -> dict:
    label = f"TEST2_{unit}"
    receipt = remote_json(f"{remote}/{label}/phase.json")
    validation = remote_json(f"{remote}/{label}/run/validation.json")
    if (
        receipt.get("state") != "success"
        or receipt.get("archive_state") != "verified"
        or receipt.get("session_id") != session
        or receipt.get("label") != label
        or receipt.get("unit") != unit
        or receipt.get("parent_latent") != parent
        or receipt.get("input_manifest_sha256") != manifest_sha
        or validation.get("unit") != unit
        or not validation.get("latent_output_relative")
        or not validation.get("latent", {}).get("sha256")
        or not validation.get("video", {}).get("sha256")
    ):
        raise RuntimeError(f"{unit} Drive receipt is incomplete or mismatched")
    return validation


def await_review(remote: str, logdir: Path, unit: str, validation: dict) -> None:
    label = f"TEST2_{unit}"
    review_dir = logdir / "review" / unit
    review_dir.mkdir(parents=True, exist_ok=False)
    for name in ("contact-sheet.jpg", "first-frame.jpg", "last-frame.jpg"):
        run([
            "rclone", "copyto", f"{remote}/{label}/run/{name}", str(review_dir / name),
            "--config", str(CONFIG),
        ], review_dir / f"pull-{name}.log", timeout=120)
    request = {"unit": unit, "prompt_id": validation["prompt_id"],
               "video_sha256": validation["video"]["sha256"],
               "requested_at_utc": datetime.now(timezone.utc).isoformat()}
    (review_dir / "review-request.json").write_text(
        json.dumps(request, indent=2) + "\n", encoding="utf-8")
    print("TEST2_REVIEW_REQUIRED", str(review_dir), json.dumps(request), flush=True)
    decision_file = review_dir / "decision.json"
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        if decision_file.is_file():
            decision = json.loads(decision_file.read_text(encoding="utf-8"))
            if (
                decision.get("unit") != unit
                or decision.get("prompt_id") != request["prompt_id"]
                or decision.get("video_sha256") != request["video_sha256"]
            ):
                raise RuntimeError(f"{unit} review decision does not match this output")
            if decision.get("decision") != "continue":
                raise RuntimeError(f"{unit} review stopped production")
            print("TEST2_REVIEW_ACCEPTED", unit, flush=True)
            return
        time.sleep(5)
    raise TimeoutError(f"{unit} review timed out; stop paid assignment")


def execute(session: str, wheel: Path, wheel_sha: str, manifest: dict,
            safety_hours: float, max_cu: float) -> None:
    logdir = BACKUP / "test2-ep01" / "sessions" / session
    logdir.mkdir(parents=True, exist_ok=False)
    session_remote = f"{REMOTE_ROOT}/{session}"
    snapshots = logdir / "cu-snapshots.jsonl"
    before = snapshot(snapshots, "before_assignment")
    sessions = run(["colab", "sessions"], logdir / "sessions-before.log", timeout=30)
    if (before["active"] or before["rate"] or before["balance"] < max_cu
            or "No active sessions" not in sessions):
        raise RuntimeError("Colab is not idle or balance is below the 40-CU safety cap")
    manifest_sha = sha256(MANIFEST)
    (logdir / "trial-inputs.json").write_text(json.dumps({
        "session": session, "remote": session_remote, "units": list(UNITS),
        "manifest_sha256": manifest_sha, "wheel_sha256": wheel_sha,
        "safety_hours": safety_hours, "max_cu": max_cu, "before": before,
    }, indent=2) + "\n", encoding="utf-8")
    created = False
    watcher = None
    started = time.monotonic()
    deadline = datetime.now(timezone.utc) + timedelta(hours=safety_hours)
    try:
        created = True
        run(["colab", "new", "--session", session, "--gpu", "G4"],
            logdir / "assignment.log", timeout=180)
        assigned = snapshot(snapshots, "assigned")
        if assigned["active"] != 1 or assigned["rate"] <= 0:
            raise RuntimeError("G4 paid assignment was not confirmed")
        if assigned["rate"] * safety_hours > max_cu:
            raise RuntimeError("assigned rate or balance exceeds 40-CU safety gate")
        with (logdir / "watchdog.log").open("w") as stream:
            watcher = subprocess.Popen(
                ["bash", str(SCRIPTS / "colab_h3_paid_watchdog.sh"),
                 session, deadline.isoformat()],
                stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        time.sleep(0.2)
        if watcher.poll() is not None:
            raise RuntimeError("paid-session watchdog exited before setup")
        print("TEST2_G4_SESSION", session, "deadline", deadline.isoformat(), flush=True)
        for source, destination in (*UPLOADS, *EXTRA_UPLOADS,
                                    (wheel, "/content/" + wheel.name)):
            run(["colab", "upload", "--session", session, str(source), destination],
                logdir / ("upload-" + source.name + ".log"), timeout=300)
        stages = (
            ("identity", SCRIPTS / "h3_g4_identity.py", 60, {}),
            ("preinstall", SCRIPTS / "colab_h3_preinstall_torch.py", 720, {}),
            ("restore", SCRIPTS / "colab_h3_restore.py", 2400, {}),
            ("setup", SCRIPTS / "h3_g4_setup.py", 900,
             {"H3_G4_WHEEL_SHA256": wheel_sha}),
            ("preflight", SCRIPTS / "h3_a100_ab_preflight.py", 600,
             {"H3_AB_PREFLIGHT_REMOTE": session_remote,
              "H3_GPU_ADAPT_EXPECTED_SHA256": RESTORED_GPU_ADAPT_SHA256}),
            ("inputs", SCRIPTS / "h3_test2_ep01_inputs.py", 600,
             {"H3_TEST2_REMOTE": session_remote}),
        )
        for name, path, timeout, env in stages:
            began = time.monotonic()
            exec_file(session, path, timeout, logdir / f"{name}.log", **env)
            marker = "TEST2_EP01_INPUTS_READY" if name == "inputs" else STAGE_MARKERS[name]
            if marker not in (logdir / f"{name}.log").read_text(errors="replace"):
                raise RuntimeError(f"{name} stage has no success marker")
            if name == "preflight":
                verify_preflight(session_remote)
            if name == "inputs":
                verify_inputs(session_remote, manifest)
            state = snapshot(snapshots, name)
            with (logdir / "stage-timing.jsonl").open("a") as stream:
                stream.write(json.dumps({
                    "stage": name, "elapsed_s": round(time.monotonic() - began, 2),
                    "rate_cu_per_hour": state["rate"], "balance_cu": state["balance"],
                }) + "\n")
        parent_path: str | None = None
        for unit in UNITS:
            if PARENTS[unit] is None:
                parent_path = None
            state = snapshot(snapshots, f"before_{unit}")
            admit_next(state, before["balance"], started, max_cu, deadline, 2100)
            began = time.monotonic()
            remote = unit_remote(session_remote, unit)
            phase_log = logdir / f"TEST2_{unit}.log"
            env = {"H3_TEST2_REMOTE": remote, "H3_TEST2_UNIT": unit}
            if parent_path:
                env["H3_TEST2_PARENT_LATENT"] = parent_path
            try:
                exec_file(
                    session, SCRIPTS / "h3_test2_ep01_phase.py", 3600, phase_log,
                    phase_label=f"TEST2_{unit}",
                    receipt_path=f"{remote}/TEST2_{unit}/phase.json",
                    input_manifest_sha256=manifest_sha, **env,
                )
            except (RuntimeError, TimeoutError):
                verify_unit(remote, session, unit, parent_path, manifest_sha)
            validation = verify_unit(remote, session, unit, parent_path, manifest_sha)
            parent_path = validation["latent_output_relative"]
            state = snapshot(snapshots, f"after_{unit}")
            with (logdir / "stage-timing.jsonl").open("a") as stream:
                stream.write(json.dumps({
                    "stage": unit, "elapsed_s": round(time.monotonic() - began, 2),
                    "rate_cu_per_hour": state["rate"], "balance_cu": state["balance"],
                }) + "\n")
            print("TEST2_UNIT_VERIFIED", unit, remote, flush=True)
            if unit in REVIEW_UNITS:
                await_review(remote, logdir, unit, validation)
    finally:
        if created:
            try:
                stop_and_verify(session, logdir, watcher)
            finally:
                (logdir / "host-wall-s.txt").write_text(
                    f"{round(time.monotonic() - started, 2)}\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-paid", action="store_true")
    parser.add_argument("--safety-hours", type=float, default=4.0)
    parser.add_argument("--max-cu", type=float, default=40.0)
    args = parser.parse_args()
    if args.safety_hours != 4.0 or args.max_cu != 40.0:
        raise ValueError("first Test2 EP01 session is authorized for 4 hours / 40 CU only")
    wheel, wheel_sha, manifest = local_inputs()
    session = "h3-test2-ep01-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    if not args.execute_paid:
        print(json.dumps({
            "ready": True, "paid_started": False, "session": session,
            "units": list(UNITS), "review_units": sorted(REVIEW_UNITS),
            "manifest_sha256": sha256(MANIFEST), "wheel_sha256": wheel_sha,
            "safety_hours": args.safety_hours, "max_cu": args.max_cu,
        }, indent=2))
        return
    execute(session, wheel, wheel_sha, manifest, args.safety_hours, args.max_cu)


if __name__ == "__main__":
    main()
