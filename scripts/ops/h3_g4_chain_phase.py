"""Run, validate and archive one G4 chain unit; never retry an uncertain prompt."""

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

sys.path.insert(0, "/content")
from h3_a100_ab_contract import parse_step_timing
from h3_a100_ab_phase import monitor_progress, start_telemetry, stop_comfy
from h3_a100_phase_receipt import identity_from_environment, publish_verified
from h3_g4_u02_phase import start_comfy


CONTENT = Path("/content")
COMFY = CONTENT / "h3-rental/ComfyUI"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def check_parent(unit: str, parent: str) -> None:
    path = (COMFY / "output" / parent).resolve()
    if not path.is_relative_to((COMFY / "output").resolve()) or not path.is_file():
        raise RuntimeError(f"missing server-side parent latent: {parent}")
    if unit == "U03":
        report = json.loads((CONTENT / "g4-chain-inputs.json").read_text())
        expected = report["parent_sha256"]
    else:
        previous = f"U{int(unit[1:]) - 1:02d}"
        validation = json.loads((CONTENT / "h3-g4-chain" / previous / "run/validation.json").read_text())
        expected = validation["latent"]["sha256"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise RuntimeError(f"{unit} parent latent changed after verification")


def run_child(unit: str, output: Path) -> None:
    with (output / "runner.log").open("w") as stream:
        completed = subprocess.run([str(COMFY / ".venv/bin/python"),
                                    "/content/h3_g4_chain_child.py"],
                                   cwd="/content/h3-runner", env=os.environ.copy(),
                                   stdout=stream, stderr=subprocess.STDOUT,
                                   timeout=2700, check=False)
    if completed.returncode:
        raise RuntimeError(f"{unit} child exited {completed.returncode}")


def validate_timing(output: Path) -> None:
    log = (output / "comfyUI.log").read_text(errors="replace")
    if "Applying MiniMax H3 Memory Efficient Sage Attention Patch" not in log:
        raise RuntimeError("SageAttention patch was not applied")
    timing = parse_step_timing(log)
    (output / "steps.json").write_text(json.dumps({
        "step_elapsed_s": timing.elapsed_seconds,
        "step_intervals_2_to_12_s": timing.intervals_seconds,
        "sampler_wall_s": timing.elapsed_seconds[-1],
        "median_step_2_to_12_s": statistics.median(timing.intervals_seconds),
    }, indent=2) + "\n")


def main() -> None:
    unit = os.environ["H3_G4_CHAIN_UNIT"]
    parent = os.environ["H3_G4_PARENT_LATENT"]
    remote = os.environ["H3_G4_REMOTE"]
    if unit not in {"U03", "U04", "U05"}:
        raise RuntimeError(f"unexpected chain unit: {unit}")
    output = CONTENT / "h3-g4-chain" / unit
    if output.exists():
        raise RuntimeError(f"{unit} already attempted; refusing an automatic retry")
    report = json.loads((CONTENT / "g4-chain-inputs.json").read_text())
    if report.get("state") != "ready" or unit not in report.get("units", []):
        raise RuntimeError("frozen chain inputs did not pass")
    check_parent(unit, parent)
    output.mkdir(parents=True)
    label = f"G4_{unit}"
    identity = identity_from_environment(label, CONTENT / "g4-chain-input-manifest.json")
    started = time.monotonic()
    result = {**vars(identity), "unit": unit, "parent_latent": parent,
              "gpu_profile": "rtx5090", "started_at_utc": now(),
              "startup_sha256": hashlib.sha256(
                  (CONTENT / "h3-runner/scripts/ops/comfy_gpu_start.sh").read_bytes()).hexdigest()}
    gpu_process = None
    gpu_stream = None
    progress_stop = threading.Event()
    progress_events: list[dict] = []
    progress_thread = None
    try:
        stop_comfy()
        start_comfy(output / "comfyUI.log")
        gpu_process, gpu_stream = start_telemetry(output / "nvidia-smi.csv")
        progress_thread = threading.Thread(target=monitor_progress,
                                           args=(output / "comfyUI.log", progress_stop,
                                                 progress_events), daemon=True)
        progress_thread.start()
        run_child(unit, output)
        validate_timing(output)
        result["state"] = "success"
    except Exception as exc:
        result["state"] = "failed"
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        progress_stop.set()
        if progress_thread is not None:
            progress_thread.join(timeout=5)
        (output / "step-observations.json").write_text(json.dumps(progress_events, indent=2) + "\n")
        if gpu_process is not None:
            gpu_process.terminate()
            try:
                gpu_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                gpu_process.kill()
                gpu_process.wait(timeout=5)
        if gpu_stream is not None:
            gpu_stream.close()
        if result["state"] == "success" and len(progress_events) != 12:
            result["state"] = "failed"
            result["progress_error"] = f"observed {len(progress_events)} of 12 steps"
        if not (output / "nvidia-smi.csv").is_file() or not (output / "nvidia-smi.csv").read_text().strip():
            result["state"] = "failed"
            result["telemetry_error"] = "nvidia-smi produced no samples"
        try:
            stop_comfy()
        except RuntimeError as exc:
            result["state"] = "failed"
            result["stop_error"] = str(exc)
        result["finished_at_utc"] = now()
        result["wall_s"] = round(time.monotonic() - started, 2)
        (output / "phase.json").write_text(json.dumps(result, indent=2) + "\n")
        publish_verified(output, f"{remote}/{label}", CONTENT / "rclone",
                         CONTENT / "rclone.conf", timeout=1200)
    print("G4_CHAIN_PHASE_RESULT", json.dumps(result), flush=True)
    if result["state"] != "success":
        raise RuntimeError(f"{unit} failed; chain stopped without another prompt")


if __name__ == "__main__":
    main()
