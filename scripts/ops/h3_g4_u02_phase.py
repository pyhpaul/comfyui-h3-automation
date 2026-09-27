"""Run and archive one process-cold G4 U02, with telemetry and a terminal receipt."""

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


OUTPUT = Path("/content/h3-g4-u02")
COMFY = Path("/content/h3-rental/ComfyUI")
REMOTE = os.environ["H3_G4_REMOTE"]
LABEL = "G4_U02"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def start_comfy(log: Path) -> None:
    env = os.environ.copy()
    env["COMFY_ROOT"] = str(COMFY)
    env["COMFY_H3_LOG"] = str(log)
    start = Path("/content/h3-runner/scripts/ops/comfy_gpu_start.sh")
    process = subprocess.Popen(["bash", str(start)], env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               start_new_session=True)
    for _ in range(90):
        if process.poll() is not None:
            raise RuntimeError(f"ComfyUI exited during startup: {process.returncode}")
        try:
            with urlopen("http://127.0.0.1:8188/system_stats", timeout=3) as response:
                stats = json.load(response)
            name = stats["devices"][0]["name"]
            if "RTX PRO 6000" not in name:
                raise RuntimeError(f"unexpected ComfyUI device: {name}")
            return
        except (OSError, KeyError, IndexError, ValueError):
            time.sleep(2)
    raise RuntimeError("ComfyUI did not become ready")


def main() -> None:
    if OUTPUT.exists():
        raise RuntimeError(f"G4 trial output already exists: {OUTPUT}")
    preflight = Path("/content/h3-a100-ab/preflight.json")
    if not preflight.is_file():
        raise RuntimeError("frozen input preflight is missing")
    preflight_report = json.loads(preflight.read_text())
    if (len(preflight_report.get("assets", [])) != 13
            or not all(item.get("match") for item in preflight_report["assets"])
            or not preflight_report.get("parent_match")):
        raise RuntimeError("frozen input preflight did not pass; do not submit U02")
    OUTPUT.mkdir()
    identity = identity_from_environment(LABEL, preflight)
    started = time.monotonic()
    result = {**vars(identity), "gpu_profile": "rtx5090", "started_at_utc": now(),
              "startup_sha256": hashlib.sha256(
                  Path("/content/h3-runner/scripts/ops/comfy_gpu_start.sh").read_bytes()).hexdigest()}
    gpu_process = None
    gpu_stream = None
    progress_stop = threading.Event()
    progress_events: list[dict] = []
    progress_thread = None
    try:
        stop_comfy()
        start_comfy(OUTPUT / "comfyUI.log")
        gpu_process, gpu_stream = start_telemetry(OUTPUT / "nvidia-smi.csv")
        progress_thread = threading.Thread(target=monitor_progress,
                                           args=(OUTPUT / "comfyUI.log", progress_stop,
                                                 progress_events), daemon=True)
        progress_thread.start()
        with (OUTPUT / "runner.log").open("w") as stream:
            completed = subprocess.run([str(COMFY / ".venv/bin/python"),
                                        "/content/h3_g4_u02_child.py"],
                                       cwd="/content/h3-runner", env=os.environ.copy(),
                                       stdout=stream, stderr=subprocess.STDOUT,
                                       timeout=2700, check=False)
        result["child_exit_code"] = completed.returncode
        if completed.returncode:
            raise RuntimeError(f"G4 U02 child exited {completed.returncode}")
        log = (OUTPUT / "comfyUI.log").read_text(errors="replace")
        if "Applying MiniMax H3 Memory Efficient Sage Attention Patch" not in log:
            raise RuntimeError("SageAttention patch was not applied")
        timing = parse_step_timing(log)
        (OUTPUT / "steps.json").write_text(json.dumps({
            "step_elapsed_s": timing.elapsed_seconds,
            "step_intervals_2_to_12_s": timing.intervals_seconds,
            "sampler_wall_s": timing.elapsed_seconds[-1],
            "median_step_2_to_12_s": statistics.median(timing.intervals_seconds),
        }, indent=2) + "\n")
        result["state"] = "success"
    except Exception as exc:
        result["state"] = "failed"
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        progress_stop.set()
        if progress_thread is not None:
            progress_thread.join(timeout=5)
        (OUTPUT / "step-observations.json").write_text(json.dumps(progress_events, indent=2) + "\n")
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
            result["progress_error"] = f"observed {len(progress_events)} of 12 step boundaries"
        if not (OUTPUT / "nvidia-smi.csv").is_file() or not (OUTPUT / "nvidia-smi.csv").read_text().strip():
            result["state"] = "failed"
            result["telemetry_error"] = "nvidia-smi produced no GPU samples"
        try:
            stop_comfy()
        except RuntimeError as exc:
            result["state"] = "failed"
            result["stop_error"] = str(exc)
        result["finished_at_utc"] = now()
        result["wall_s"] = round(time.monotonic() - started, 2)
        (OUTPUT / "phase.json").write_text(json.dumps(result, indent=2) + "\n")
        publish_verified(OUTPUT, f"{REMOTE}/{LABEL}", Path("/content/rclone"),
                         Path("/content/rclone.conf"), timeout=1200)
    print("G4_U02_PHASE_RESULT", json.dumps(result), flush=True)
    if result["state"] != "success":
        raise RuntimeError("G4 U02 failed; do not submit another prompt")


if __name__ == "__main__":
    main()
