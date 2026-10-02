"""One supervised G4 assignment for frozen EP04 U03-U05, with per-unit backup."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from colab_h3_a100_ab_host import exec_file, run, snapshot, stop_and_verify
from colab_h3_g4_u02_host import (
    BACKUP, CONFIG, SCRIPTS, UPLOADS, STAGE_MARKERS, WHEEL_DIR,
    local_preflight, remote_json, setup_stages, verify_preflight,
)


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/ops/drive-chain-ep04-u03-u05-v1.json"
LOCAL_ARCHIVE = BACKUP / "g4-chain/inputs/ep04-manual-v16-u03-u05.tar"
REMOTE_ROOT = "h3drive_h3:comfyui-h3-colab-dedicated/standard-v1/runs/ep04"
PARENTS = {
    "U03": "h3_context/ep04_u02_g4_u02_00002.safetensors",
    "U04": "h3_context/ep04_u03_00003.safetensors",
    "U05": "h3_context/ep04_u04_00004.safetensors",
}
EXTRA_UPLOADS = (
    (MANIFEST, "/content/g4-chain-input-manifest.json"),
    (SCRIPTS / "h3_g4_u02_phase.py", "/content/h3_g4_u02_phase.py"),
    (SCRIPTS / "h3_g4_chain_contract.py", "/content/h3_g4_chain_contract.py"),
    (SCRIPTS / "h3_g4_chain_media.py", "/content/h3_g4_chain_media.py"),
    (SCRIPTS / "h3_g4_chain_child.py", "/content/h3_g4_chain_child.py"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def remote_file_matches(record: dict) -> bool:
    result = subprocess.run(["rclone", "lsjson", record["remote"], "--stat", "--hash",
                             "--config", str(CONFIG)], capture_output=True, check=True,
                            timeout=30)
    remote = json.loads(result.stdout)
    return (remote.get("Size") == record["bytes"]
            and remote.get("Hashes", {}).get("sha256") == record["sha256"])


def local_inputs() -> tuple[Path, str, dict]:
    wheel, wheel_sha = local_preflight()
    manifest = json.loads(MANIFEST.read_text())
    if (manifest.get("units") != list(PARENTS)
            or manifest["parent_latent"]["output_relative_path"] != PARENTS["U03"]
            or not LOCAL_ARCHIVE.is_file()
            or LOCAL_ARCHIVE.stat().st_size != manifest["job_archive"]["bytes"]
            or sha256(LOCAL_ARCHIVE) != manifest["job_archive"]["sha256"]):
        raise RuntimeError("local G4 chain inputs do not match the frozen manifest")
    for key in ("job_archive", "parent_latent"):
        if not remote_file_matches(manifest[key]):
            raise RuntimeError(f"Drive {key} differs from the frozen manifest")
    missing = [str(path) for path, _ in EXTRA_UPLOADS if not path.is_file()]
    missing.extend(str(SCRIPTS / name) for name in
                   ("h3_g4_chain_inputs.py", "h3_g4_chain_phase.py")
                   if not (SCRIPTS / name).is_file())
    if missing:
        raise RuntimeError(f"missing chain scripts: {missing}")
    return wheel, wheel_sha, manifest


def verify_chain_inputs(remote: str, manifest: dict) -> None:
    report = remote_json(f"{remote}/chain-inputs.json")
    if (report.get("state") != "ready" or report.get("units") != list(PARENTS)
            or report.get("archive_sha256") != manifest["job_archive"]["sha256"]
            or report.get("parent_sha256") != manifest["parent_latent"]["sha256"]
            or report.get("parent_path") != PARENTS["U03"]):
        raise RuntimeError("remote chain input admission failed")


def verify_unit(remote: str, session: str, unit: str, manifest_sha: str) -> dict:
    receipt = remote_json(f"{remote}/G4_{unit}/phase.json")
    validation = remote_json(f"{remote}/G4_{unit}/run/validation.json")
    if (receipt.get("state") != "success" or receipt.get("archive_state") != "verified"
            or receipt.get("session_id") != session or receipt.get("label") != f"G4_{unit}"
            or receipt.get("unit") != unit or receipt.get("parent_latent") != PARENTS[unit]
            or receipt.get("input_manifest_sha256") != manifest_sha
            or validation.get("unit") != unit or not validation.get("latent", {}).get("sha256")
            or not validation.get("video", {}).get("sha256")):
        raise RuntimeError(f"{unit} verified Drive receipt is incomplete or mismatched")
    return receipt


def chain_setup_stages(wheel_sha: str, remote: str, restore_workers: int
                       ) -> tuple[tuple[str, Path, int, dict[str, str]], ...]:
    return (*setup_stages(wheel_sha, remote, restore_workers),
            ("chain_inputs", SCRIPTS / "h3_g4_chain_inputs.py", 600,
             {"H3_G4_REMOTE": remote}))


def execute(session: str, wheel: Path, wheel_sha: str, manifest: dict,
            safety_hours: float, max_cu: float, restore_workers: int = 4) -> None:
    logdir = BACKUP / "g4-chain" / session
    logdir.mkdir(parents=True, exist_ok=False)
    chain_remote = f"{REMOTE_ROOT}/chain/{session}"
    snapshots = logdir / "cu-snapshots.jsonl"
    before = snapshot(snapshots, "before_assignment")
    sessions = run(["colab", "sessions"], logdir / "sessions-before.log", timeout=30)
    if before["active"] or before["rate"] or "No active sessions" not in sessions:
        raise RuntimeError("Colab is not idle; no G4 assignment created")
    manifest_sha = sha256(MANIFEST)
    (logdir / "trial-inputs.json").write_text(json.dumps({
        "session": session, "chain_remote": chain_remote, "units": list(PARENTS),
        "manifest_sha256": manifest_sha, "wheel_sha256": wheel_sha,
        "safety_hours": safety_hours, "max_cu": max_cu, "before": before,
        "restore_workers": restore_workers,
    }, indent=2) + "\n")
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
            raise RuntimeError("G4 rate exceeds the frozen CU safety budget")
        with (logdir / "watchdog.log").open("w") as stream:
            watcher = subprocess.Popen(
                ["bash", str(SCRIPTS / "colab_h3_paid_watchdog.sh"),
                 session, deadline.isoformat()], stdin=subprocess.DEVNULL,
                stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        time.sleep(0.2)
        if watcher.poll() is not None:
            raise RuntimeError("paid-session watchdog exited before setup")
        print("G4_CHAIN_SESSION", session, "deadline", deadline.isoformat(), flush=True)
        for source, destination in (*UPLOADS, *EXTRA_UPLOADS,
                                    (wheel, "/content/" + wheel.name)):
            run(["colab", "upload", "--session", session, str(source), destination],
                logdir / ("upload-" + source.name + ".log"), timeout=300)
        stages = chain_setup_stages(wheel_sha, chain_remote, restore_workers)
        for name, path, timeout, env in stages:
            began = time.monotonic()
            exec_file(session, path, timeout, logdir / f"{name}.log", **env)
            marker = ("G4_CHAIN_INPUTS_READY" if name == "chain_inputs"
                      else STAGE_MARKERS[name])
            if marker not in (logdir / f"{name}.log").read_text(errors="replace"):
                raise RuntimeError(f"{name} stage has no success marker")
            if name == "preflight":
                verify_preflight(chain_remote)
            if name == "chain_inputs":
                verify_chain_inputs(chain_remote, manifest)
            state = snapshot(snapshots, name)
            (logdir / "stage-timing.jsonl").open("a").write(json.dumps({
                "stage": name, "elapsed_s": round(time.monotonic() - began, 2),
                "rate_cu_per_hour": state["rate"], "balance_cu": state["balance"],
            }) + "\n")
        for unit in PARENTS:
            began = time.monotonic()
            remote = f"{REMOTE_ROOT}/{unit.lower()}/{session}"
            phase_log = logdir / f"G4_{unit}.log"
            try:
                exec_file(session, SCRIPTS / "h3_g4_chain_phase.py", 4200, phase_log,
                          phase_label=f"G4_{unit}", receipt_path=f"{remote}/G4_{unit}/phase.json",
                          input_manifest_sha256=manifest_sha,
                          H3_G4_REMOTE=remote, H3_G4_CHAIN_UNIT=unit,
                          H3_G4_PARENT_LATENT=PARENTS[unit])
            except (RuntimeError, TimeoutError):
                verify_unit(remote, session, unit, manifest_sha)
            verify_unit(remote, session, unit, manifest_sha)
            state = snapshot(snapshots, f"after_{unit}")
            (logdir / "stage-timing.jsonl").open("a").write(json.dumps({
                "stage": unit, "elapsed_s": round(time.monotonic() - began, 2),
                "rate_cu_per_hour": state["rate"], "balance_cu": state["balance"],
            }) + "\n")
            print("G4_CHAIN_UNIT_VERIFIED", unit, remote, flush=True)
    finally:
        if created:
            try:
                stop_and_verify(session, logdir, watcher)
            finally:
                for unit in PARENTS:
                    remote = f"{REMOTE_ROOT}/{unit.lower()}/{session}"
                    try:
                        run(["rclone", "copy", remote, str(logdir / "evidence" / unit),
                             "--config", str(CONFIG), "--exclude", "*.mp4",
                             "--exclude", "*.safetensors"], timeout=300)
                    except (RuntimeError, TimeoutError) as exc:
                        print("EVIDENCE_PULL_UNAVAILABLE", unit, exc, flush=True)
                (logdir / "host-wall-s.txt").write_text(
                    f"{round(time.monotonic() - started, 2)}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-paid", action="store_true")
    parser.add_argument("--safety-hours", type=float, default=2.0)
    parser.add_argument("--max-cu", type=float, default=20.0)
    parser.add_argument("--restore-workers", type=int, choices=(1, 4), default=4,
                        help="four-worker restore, or explicit original serial rollback")
    args = parser.parse_args()
    if not 2 <= args.safety_hours <= 8:
        raise ValueError("safety deadline must be between two and eight hours")
    if args.max_cu <= 0:
        raise ValueError("CU safety budget must be positive")
    wheel, wheel_sha, manifest = local_inputs()
    session = "h3-g4-chain-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    if not args.execute_paid:
        print(json.dumps({"ready": True, "paid_started": False, "session": session,
                          "units": list(PARENTS), "manifest_sha256": sha256(MANIFEST),
                          "wheel_sha256": wheel_sha, "safety_hours": args.safety_hours,
                          "max_cu": args.max_cu, "restore_workers": args.restore_workers}, indent=2))
        return
    execute(session, wheel, wheel_sha, manifest, args.safety_hours, args.max_cu,
            args.restore_workers)


if __name__ == "__main__":
    main()
