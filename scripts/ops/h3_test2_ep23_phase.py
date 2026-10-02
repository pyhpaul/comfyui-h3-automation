"""Supervised single-attempt Test2 EP02/EP03 G4 unit phase."""

from __future__ import annotations

import hashlib
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

sys.path.insert(0, "/content")
from h3_a100_ab_contract import parse_step_timing
from h3_a100_ab_phase import monitor_progress, start_telemetry, stop_comfy
from h3_a100_phase_receipt import identity_from_environment, publish_verified
from h3_test2_ep23_contract import parent_unit


CONTENT = Path("/content")
COMFY = CONTENT / "h3-rental/ComfyUI"
OUTPUT_ROOT = CONTENT / "h3-test2-ep23"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def start_comfy(log: Path) -> None:
    env = os.environ.copy()
    env["COMFY_ROOT"] = str(COMFY)
    env["COMFY_H3_LOG"] = str(log)
    script = CONTENT / "h3-runner/scripts/ops/comfy_gpu_start.sh"
    process = subprocess.Popen(["bash", str(script)], env=env,
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(90):
        if process.poll() is not None:
            raise RuntimeError(f"ComfyUI exited during startup: {process.returncode}")
        try:
            with urlopen("http://127.0.0.1:8188/system_stats", timeout=3) as response:
                stats = json.load(response)
            if "RTX PRO 6000" not in stats["devices"][0]["name"]:
                raise RuntimeError("ComfyUI did not start on the G4 GPU")
            return
        except (OSError, KeyError, IndexError, ValueError):
            time.sleep(2)
    raise RuntimeError("ComfyUI did not become ready")


def check_parent(episode: str, unit: str, parent_path: str | None) -> None:
    expected = parent_unit(episode, unit)
    if expected is None:
        if parent_path:
            raise RuntimeError(f"{episode} {unit} independent start received a latent")
        return
    expected_sha = os.environ.get("H3_TEST2_PARENT_SHA256")
    if not parent_path or not expected_sha:
        raise RuntimeError(f"{episode} {unit} requires verified {expected} latent and SHA-256")
    output_root = (COMFY / "output").resolve()
    path = (output_root / parent_path).resolve()
    if not path.is_relative_to(output_root) or not path.is_file():
        raise RuntimeError(f"server-side parent latent is missing: {parent_path}")
    if file_sha256(path) != expected_sha:
        raise RuntimeError(f"{episode} {unit} parent latent SHA-256 mismatch")


def run_child(output: Path) -> None:
    with (output / "runner.log").open("w") as stream:
        completed = subprocess.run(
            [str(COMFY / ".venv/bin/python"), "/content/h3_test2_ep23_child.py"],
            cwd="/content/h3-runner", env=os.environ.copy(), stdout=stream,
            stderr=subprocess.STDOUT, timeout=3000, check=False,
        )
    if completed.returncode:
        raise RuntimeError(f"Test2 child exited {completed.returncode}")


def validate_timing(output: Path) -> None:
    log = (output / "comfyUI.log").read_text(errors="replace")
    if "Applying MiniMax H3 Memory Efficient Sage Attention Patch" not in log:
        raise RuntimeError("G4 SageAttention patch was not applied")
    timing = parse_step_timing(log)
    (output / "steps.json").write_text(json.dumps({
        "step_elapsed_s": timing.elapsed_seconds,
        "step_intervals_2_to_12_s": timing.intervals_seconds,
        "sampler_wall_s": timing.elapsed_seconds[-1],
        "median_step_2_to_12_s": statistics.median(timing.intervals_seconds),
    }, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    episode = os.environ["H3_TEST2_EPISODE"]
    unit = os.environ["H3_TEST2_UNIT"]
    parent_path = os.environ.get("H3_TEST2_PARENT_LATENT") or None
    parent_unit(episode, unit)
    attempt = os.environ["H3_ATTEMPT_ID"]
    output = OUTPUT_ROOT / episode / unit / attempt
    if output.exists():
        raise RuntimeError("attempt directory already exists; inspect before retry")
    inputs = json.loads((CONTENT / "test2-ep23-inputs.json").read_text(encoding="utf-8"))
    if inputs.get("state") != "ready" or unit not in inputs.get("episodes", {}).get(episode, []):
        raise RuntimeError("accepted Test2 inputs were not installed")
    check_parent(episode, unit, parent_path)
    output.mkdir(parents=True)
    os.environ["H3_TEST2_ATTEMPT_DIR"] = str(output)
    label = f"{episode}_{unit}"
    identity = identity_from_environment(label, CONTENT / "test2-ep23-input-manifest.json")
    started = time.monotonic()
    result = {
        **vars(identity), "episode": episode, "unit": unit,
        "parent_latent": parent_path, "gpu_profile": "rtx5090",
        "started_at_utc": now(),
        "startup_sha256": file_sha256(
            CONTENT / "h3-runner/scripts/ops/comfy_gpu_start.sh"),
    }
    gpu_process = None
    gpu_stream = None
    progress_stop = threading.Event()
    progress_events: list[dict] = []
    progress_thread = None
    try:
        stop_comfy()
        start_comfy(output / "comfyUI.log")
        gpu_process, gpu_stream = start_telemetry(output / "nvidia-smi.csv")
        progress_thread = threading.Thread(
            target=monitor_progress,
            args=(output / "comfyUI.log", progress_stop, progress_events), daemon=True)
        progress_thread.start()
        run_child(output)
        validate_timing(output)
        result["state"] = "success"
    except Exception as exc:
        result["state"] = "failed"
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        progress_stop.set()
        if progress_thread is not None:
            progress_thread.join(timeout=5)
        if gpu_process is not None:
            gpu_process.terminate()
            try:
                gpu_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                gpu_process.kill()
                gpu_process.wait(timeout=5)
        if gpu_stream is not None:
            gpu_stream.close()
        (output / "step-observations.json").write_text(
            json.dumps(progress_events, indent=2) + "\n", encoding="utf-8")
        if result["state"] == "success" and len(progress_events) != 12:
            result["state"] = "failed"
            result["progress_error"] = f"observed {len(progress_events)} of 12 steps"
        if not (output / "nvidia-smi.csv").is_file() or not (
            output / "nvidia-smi.csv").read_text().strip():
            result["state"] = "failed"
            result["telemetry_error"] = "nvidia-smi produced no samples"
        try:
            stop_comfy()
        except RuntimeError as exc:
            result["state"] = "failed"
            result["stop_error"] = str(exc)
        result["finished_at_utc"] = now()
        result["wall_s"] = round(time.monotonic() - started, 2)
        (output / "phase.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8")
        remote = os.environ["H3_TEST2_REMOTE"]
        publish_verified(output, remote, CONTENT / "rclone",
                         CONTENT / "rclone.conf", timeout=1200)
    print("TEST2_EP23_PHASE_RESULT", json.dumps(result), flush=True)
    if result["state"] != "success":
        raise RuntimeError(f"{episode} {unit} failed; inspect receipt before retry")


if __name__ == "__main__":
    main()
