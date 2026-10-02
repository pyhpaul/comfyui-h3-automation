"""Process-cold, single-run Colab A100 phase with per-run Drive backup."""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

sys.path.insert(0, "/content")
from h3_a100_ab_contract import (FORMAL_RUNS, MEMORY_FORMAL_RUNS, RUN_PROFILES, improvement_fraction,
                                  parse_step_timing, timing_pair_passes)
from h3_a100_phase_receipt import identity_from_environment, publish_verified


CONTENT = Path("/content")
COMFY = CONTENT / "h3-rental/ComfyUI"
RUNNER = CONTENT / "h3-runner"
REMOTE = "h3drive_h3:comfyui-h3-colab-dedicated/rental-20260924-5090/a100-perf-pilot/formal-ab-1"
ORDER = ("P_B", "P_C", "B1", "C1", "B2", "C2")
MEMORY_ORDER = ("S1", "M1", "S2", "M2")
MEMORY_START = CONTENT / "h3_a100_memory_start.sh"
MEMORY_REMOTE_PREFIX = REMOTE.removesuffix("formal-ab-1") + "profile-h3-a100-combined-"
MAX_PROFILE_RESERVED_BYTES = 70 * 1024 ** 3
PROGRESS_RE = re.compile(rb"(?<!\d)(\d+)/12 \[")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def owned_comfy_pids() -> list[int]:
    pids = []
    for item in Path("/proc").iterdir():
        if not item.name.isdigit():
            continue
        try:
            cwd = (item / "cwd").resolve()
            command = (item / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except (OSError, PermissionError):
            continue
        if cwd == COMFY and "main.py" in command and "--port 8188" in command:
            pids.append(int(item.name))
    return pids


def stop_comfy() -> None:
    for pid in owned_comfy_pids():
        os.kill(pid, signal.SIGTERM)
    for _ in range(50):
        if not owned_comfy_pids():
            return
        time.sleep(0.2)
    raise RuntimeError(f"owned ComfyUI did not stop: {owned_comfy_pids()}")


def start_comfy(log: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["COMFY_ROOT"] = str(COMFY)
    env["COMFY_H3_LOG"] = str(log)
    start_script = Path(env.get("H3_COMFY_START_SCRIPT",
                                str(RUNNER / "scripts/ops/comfy_gpu_start.sh")))
    if not start_script.is_file():
        raise RuntimeError(f"ComfyUI start script is missing: {start_script}")
    process = subprocess.Popen(["bash", str(start_script)],
                               env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               start_new_session=True)
    for _ in range(90):
        if process.poll() is not None:
            raise RuntimeError(f"ComfyUI exited during startup: {process.returncode}")
        try:
            with urlopen("http://127.0.0.1:8188/system_stats", timeout=3) as response:
                stats = json.load(response)
            name = stats["devices"][0]["name"]
            if "A100-SXM4-80GB" not in name:
                raise RuntimeError(f"unexpected GPU: {name}")
            return process
        except (OSError, KeyError, IndexError, ValueError):
            time.sleep(2)
    raise RuntimeError("ComfyUI did not become ready")


def start_telemetry(output: Path) -> tuple[subprocess.Popen, object]:
    stream = output.open("w")
    command = ["nvidia-smi", "--query-gpu=timestamp,utilization.gpu,memory.used,power.draw,clocks.sm,temperature.gpu",
               "--format=csv,noheader,nounits", "--loop-ms=5000"]
    process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT)
    return process, stream


def monitor_progress(log: Path, stopped: threading.Event, events: list[dict]) -> None:
    offset = 0
    tail = b""
    seen = set()
    while True:
        if log.is_file():
            with log.open("rb") as stream:
                stream.seek(offset)
                fresh = stream.read()
                offset = stream.tell()
            data = tail + fresh
            for match in PROGRESS_RE.finditer(data):
                step = int(match.group(1))
                if 1 <= step <= 12 and step not in seen:
                    seen.add(step)
                    events.append({"step": step, "observed_at_utc": utc_now()})
            tail = data[-64:]
        if stopped.wait(0.5):
            return


def read_steps(label: str, log: Path, output: Path) -> None:
    if label not in FORMAL_RUNS:
        return
    timing = parse_step_timing(log.read_text(errors="replace"))
    summary = {"step_elapsed_s": timing.elapsed_seconds,
               "step_intervals_2_to_12_s": timing.intervals_seconds,
               "sampler_wall_s": timing.elapsed_seconds[-1],
               "median_step_2_to_12_s": statistics.median(timing.intervals_seconds)}
    (output / "steps.json").write_text(json.dumps(summary, indent=2) + "\n")


def verify_attention_mode(label: str, log: Path) -> None:
    applied = "Applying MiniMax H3 Memory Efficient Sage Attention Patch" in log.read_text(errors="replace")
    if applied != (RUN_PROFILES[label] == "a100_sage_sm80"):
        raise RuntimeError(f"{label} attention patch state does not match the selected profile")


def verify_memory_mode(label: str, log: Path) -> None:
    disabled = "Disabling smart memory management" in log.read_text(errors="replace")
    if disabled != label.startswith("S"):
        raise RuntimeError(f"{label} smart-memory startup flag did not match the selected mode")


def require_previous(label: str) -> None:
    if label in MEMORY_ORDER and label == "S1":
        profile = CONTENT / "h3-profile-evidence/M0"
        receipt = json.loads((profile / "phase.json").read_text())
        if receipt.get("state") != "success":
            raise RuntimeError("S1 requires a successful M0 safety profile")
        memory = json.loads((profile / "sampler-profile.json").read_text())
        if memory["peak_reserved_bytes"] > MAX_PROFILE_RESERVED_BYTES:
            raise RuntimeError("M0 profiler peak exceeds the predeclared 70 GiB safety gate")
        return
    order = MEMORY_ORDER if label in MEMORY_ORDER else ORDER
    position = order.index(label)
    if position == 0:
        return
    previous = CONTENT / "h3-a100-ab" / order[position - 1] / "phase.json"
    if not previous.is_file() or json.loads(previous.read_text()).get("state") != "success":
        raise RuntimeError(f"{label} requires a successful {order[position - 1]}")


def timing(label: str) -> dict[str, float]:
    folder = CONTENT / "h3-a100-ab" / label
    validation = json.loads((folder / "validation.json").read_text())
    steps = json.loads((folder / "steps.json").read_text())
    return {"server_wall_s": validation["server_wall_s"],
            "sampler_wall_s": steps["sampler_wall_s"]}


def screen(label: str, output: Path) -> None:
    if label not in {"C1", "C2"}:
        return
    pairs = [("B1", "C1")] if label == "C1" else [("B1", "C1"), ("B2", "C2")]
    results = []
    for baseline, candidate in pairs:
        b, c = timing(baseline), timing(candidate)
        results.append({"baseline": baseline, "candidate": candidate,
                        "server_improvement": improvement_fraction(b["server_wall_s"], c["server_wall_s"]),
                        "sampler_improvement": improvement_fraction(b["sampler_wall_s"], c["sampler_wall_s"]),
                        "passes_15_percent": timing_pair_passes(b, c)})
    baseline_spread = None
    if label == "C2":
        first, second = timing("B1"), timing("B2")
        baseline_spread = max(abs(first[key] - second[key]) / min(first[key], second[key])
                              for key in ("server_wall_s", "sampler_wall_s"))
    report = {"pairs": results, "baseline_spread": baseline_spread,
              "timing_screen_passes": all(item["passes_15_percent"] for item in results)
              and (baseline_spread is None or baseline_spread <= 0.10)}
    (output / "timing_screen.json").write_text(json.dumps(report, indent=2) + "\n")
    if not report["timing_screen_passes"]:
        raise RuntimeError("candidate did not pass the timing screen; stop the paid batch")


def memory_screen(label: str, output: Path) -> None:
    if label not in {"M1", "M2"}:
        return
    pairs = (("S1", "M1"),) if label == "M1" else (("S1", "M1"), ("S2", "M2"))
    startup_hash = hashlib.sha256(MEMORY_START.read_bytes()).hexdigest()
    previous = ("S1",) if label == "M1" else ("S1", "M1", "S2")
    prior_startups = [json.loads((CONTENT / "h3-a100-ab" / name / "phase.json").read_text())
                      for name in previous]
    same_startup_script = all(item.get("startup_sha256") == startup_hash for item in prior_startups)
    results = []
    for baseline, candidate in pairs:
        b, c = timing(baseline), timing(candidate)
        left = json.loads((CONTENT / "h3-a100-ab" / baseline / "validation.json").read_text())
        right = json.loads((CONTENT / "h3-a100-ab" / candidate / "validation.json").read_text())
        hashes_equal = (left["latent"]["sha256"] == right["latent"]["sha256"]
                        and all(left["video"][key] == right["video"][key]
                                for key in ("decoded_video_sha256", "decoded_audio_sha256")))
        results.append({"baseline": baseline, "candidate": candidate,
                        "server_improvement": improvement_fraction(b["server_wall_s"], c["server_wall_s"]),
                        "sampler_improvement": improvement_fraction(b["sampler_wall_s"], c["sampler_wall_s"]),
                        "timing_passes": timing_pair_passes(b, c),
                        "content_hashes_equal": hashes_equal})
    spread = None
    repeat_hashes_equal = None
    if label == "M2":
        first, second = timing("S1"), timing("S2")
        spread = max(abs(first[key] - second[key]) / min(first[key], second[key])
                     for key in ("server_wall_s", "sampler_wall_s"))
        validations = [json.loads((CONTENT / "h3-a100-ab" / name / "validation.json").read_text())
                       for name in MEMORY_ORDER]
        repeat_hashes_equal = all(
            validations[0][kind][key] == validations[2][kind][key]
            and validations[1][kind][key] == validations[3][kind][key]
            for kind, key in (("latent", "sha256"),
                              ("video", "decoded_video_sha256"),
                              ("video", "decoded_audio_sha256")))
    passes = (all(item["timing_passes"] and item["content_hashes_equal"] for item in results)
              and same_startup_script
              and (spread is None or spread <= 0.10)
              and (repeat_hashes_equal is None or repeat_hashes_equal))
    report = {"pairs": results, "baseline_spread": spread,
              "repeat_hashes_equal": repeat_hashes_equal,
              "same_startup_script": same_startup_script, "timing_screen_passes": passes}
    (output / "memory_timing_screen.json").write_text(json.dumps(report, indent=2) + "\n")
    if not passes:
        raise RuntimeError("memory candidate failed timing, output-hash, or stability gate")


def backup(label: str, output: Path, remote_root: str) -> None:
    remote = f"{remote_root}/{label}"
    publish_verified(output, remote, Path("/content/rclone"), Path("/content/rclone.conf"))
    print("DRIVE_BACKUP_VERIFIED", label, remote, flush=True)


def main() -> None:
    label = os.environ.get("H3_AB_RUN", "")
    if label not in RUN_PROFILES:
        raise ValueError(f"H3_AB_RUN must be one of {sorted(RUN_PROFILES)}")
    remote_root = os.environ.get("H3_AB_REMOTE", REMOTE)
    if label in MEMORY_FORMAL_RUNS and not remote_root.startswith(MEMORY_REMOTE_PREFIX):
        raise RuntimeError("memory trial requires its unique Drive evidence prefix")
    if not Path("/content/h3-a100-ab/preflight.json").is_file():
        raise RuntimeError("frozen input preflight is missing")
    require_previous(label)
    output = CONTENT / "h3-a100-ab" / label
    if output.exists():
        raise RuntimeError(f"run output already exists; do not overwrite {output}")
    output.mkdir(parents=True)
    started = time.monotonic()
    identity = identity_from_environment(label, CONTENT / "h3-a100-ab/preflight.json")
    result = {**vars(identity), "profile": RUN_PROFILES[label],
              "started_at_utc": utc_now()}
    if label in MEMORY_FORMAL_RUNS:
        if not MEMORY_START.is_file():
            raise RuntimeError("memory-trial ComfyUI start script is missing")
        os.environ["H3_COMFY_START_SCRIPT"] = str(MEMORY_START)
        os.environ["H3_DISABLE_SMART_MEMORY"] = "0" if label.startswith("M") else "1"
        result["disable_smart_memory"] = os.environ["H3_DISABLE_SMART_MEMORY"]
        result["startup_sha256"] = hashlib.sha256(MEMORY_START.read_bytes()).hexdigest()
        os.environ.pop("H3_PROFILE_SAMPLER", None)
        os.environ.pop("H3_PROFILE_OUTPUT", None)
    gpu_process = None
    gpu_stream = None
    progress_stop = threading.Event()
    progress_thread = None
    progress_events: list[dict] = []
    try:
        stop_comfy()
        start_comfy(output / "comfyUI.log")
        gpu_process, gpu_stream = start_telemetry(output / "nvidia-smi.csv")
        if label in FORMAL_RUNS:
            progress_thread = threading.Thread(target=monitor_progress,
                                               args=(output / "comfyUI.log", progress_stop,
                                                     progress_events), daemon=True)
            progress_thread.start()
        with (output / "runner.log").open("w") as stream:
            completed = subprocess.run([str(COMFY / ".venv/bin/python"),
                                        "/content/h3_a100_ab_child.py"],
                                       cwd=RUNNER, env=os.environ.copy(),
                                       stdout=stream, stderr=subprocess.STDOUT,
                                       timeout=2100 if label in FORMAL_RUNS else 420,
                                       check=False)
        result["child_exit_code"] = completed.returncode
        if completed.returncode:
            raise RuntimeError(f"{label} child failed with exit {completed.returncode}")
        verify_attention_mode(label, output / "comfyUI.log")
        if label in MEMORY_FORMAL_RUNS:
            verify_memory_mode(label, output / "comfyUI.log")
        read_steps(label, output / "comfyUI.log", output)
        screen(label, output)
        memory_screen(label, output)
        result["state"] = "success"
    except Exception as exc:
        result["state"] = "failed"
        result["error"] = str(exc)
    finally:
        progress_stop.set()
        if progress_thread is not None:
            progress_thread.join(timeout=5)
            (output / "step-observations.json").write_text(json.dumps(progress_events, indent=2) + "\n")
            if result["state"] == "success" and len(progress_events) != 12:
                result["state"] = "failed"
                result["progress_error"] = f"observed {len(progress_events)} of 12 step boundaries"
        if gpu_process is not None:
            gpu_process.terminate()
            try:
                gpu_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                gpu_process.kill()
                gpu_process.wait(timeout=5)
        if gpu_stream is not None:
            gpu_stream.close()
            if not (output / "nvidia-smi.csv").read_text().strip():
                result["state"] = "failed"
                result["telemetry_error"] = "nvidia-smi produced no GPU samples"
        try:
            stop_comfy()
        except RuntimeError as exc:
            result["state"] = "failed"
            result["stop_error"] = str(exc)
        result["finished_at_utc"] = utc_now()
        result["wall_s"] = round(time.monotonic() - started, 2)
        (output / "phase.json").write_text(json.dumps(result, indent=2) + "\n")
        backup(label, output, remote_root)
    print("AB_PHASE_RESULT", json.dumps(result), flush=True)
    if result["state"] != "success":
        raise RuntimeError(f"{label} failed; stop the paid batch")


if __name__ == "__main__":
    main()
