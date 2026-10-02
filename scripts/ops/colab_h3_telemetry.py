"""Collect phase timings, runtime samples, CU snapshots, and Comfy evidence."""

from __future__ import annotations

import argparse
import codecs
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


GPU_FIELDS = (
    "timestamp,index,name,driver_version,memory.total,memory.used,"
    "utilization.gpu,utilization.memory,temperature.gpu,power.draw"
)
MARKERS = ("RUN ", "model_part ", "restore_ready", "model_restore_seconds",
           "comfy_ready", "START ", "SUCCESS ", "FAILED ", "Prompt executed")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def emit(path: Path, event: str, **fields: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"at_utc": utc_now(), "event": event, **fields}
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def command_output(command: list[str], timeout: int = 15) -> dict[str, Any]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        return {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": str(exc)}


def snapshot(metrics_dir: Path, python: str, label: str) -> None:
    root = Path("/content/h3-rental/ComfyUI")
    details = {
        "at_utc": utc_now(),
        "label": label,
        "platform": platform.platform(),
        "uname": platform.uname()._asdict(),
        "python_executable": sys.executable,
        "python_version": sys.version,
        "cpu_count": os.cpu_count(),
        "nvidia_smi": command_output(["nvidia-smi", "-q"]),
        "nvidia_smi_csv": command_output([
            "nvidia-smi", f"--query-gpu={GPU_FIELDS}", "--format=csv,noheader,nounits"
        ]),
        "cpu": command_output(["lscpu"]),
        "memory": command_output(["free", "-b"]),
        "disk": command_output(["df", "-B1", "/content"]),
        "comfy_git_head": command_output(["git", "-C", str(root), "rev-parse", "HEAD"]),
        "torch": command_output([
            python, "-c", "import json,torch; print(json.dumps({"
            "'version':torch.__version__,'cuda':torch.version.cuda,"
            "'cudnn':torch.backends.cudnn.version(),"
            "'device':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,"
            "'capability':torch.cuda.get_device_capability(0) if torch.cuda.is_available() else None}))"
        ], timeout=45),
    }
    write_json(metrics_dir / f"environment-{label}.json", details)
    write_json(metrics_dir / f"python-packages-{label}.json",
               command_output([python, "-m", "pip", "freeze"], timeout=60))
    emit(metrics_dir / "events.jsonl", "environment_snapshot", python=python, label=label)


def runtime_sample() -> dict[str, Any]:
    gpu = command_output([
        "nvidia-smi", f"--query-gpu={GPU_FIELDS}", "--format=csv,noheader,nounits"
    ])
    memory: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            key, value = line.split(":", 1)
            if key in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
                memory[key + "_kib"] = int(value.strip().split()[0])
    except (OSError, ValueError):
        pass
    disk = shutil.disk_usage("/content") if Path("/content").exists() else None
    return {
        "gpu": gpu,
        "memory": memory,
        "disk_free_bytes": disk.free if disk else None,
        "load_average": os.getloadavg() if hasattr(os, "getloadavg") else None,
    }


def sample_until_stopped(metrics_dir: Path, phase: str, stop: threading.Event, interval: float) -> None:
    while not stop.is_set():
        emit(metrics_dir / "runtime-samples.jsonl", "runtime_sample", phase=phase, **runtime_sample())
        stop.wait(interval)


def record_output(metrics_dir: Path, phase: str, line: str) -> None:
    if not line.strip():
        return
    with (metrics_dir / f"{phase}.log").open("a", encoding="utf-8") as stream:
        stream.write(f"{utc_now()} {line}\n")
    if line.startswith(MARKERS) or "Prompt executed" in line:
        emit(metrics_dir / "events.jsonl", "process_marker", phase=phase, message=line[:1200])


def run_phase(metrics_dir: Path, phase: str, interval: float, command: list[str]) -> int:
    if not command:
        raise ValueError("a command is required after --")
    metrics_dir.mkdir(parents=True, exist_ok=True)
    events = metrics_dir / "events.jsonl"
    started = time.monotonic()
    emit(events, "phase_start", phase=phase, command=command)
    stop = threading.Event()
    monitor = threading.Thread(
        target=sample_until_stopped, args=(metrics_dir, phase, stop, interval), daemon=True
    )
    monitor.start()
    exit_code = 1
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert process.stdout is not None
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        pending = ""
        while chunk := os.read(process.stdout.fileno(), 4096):
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
            pending += decoder.decode(chunk)
            parts = re.split(r"[\r\n]", pending)
            pending = parts.pop()
            for line in parts:
                record_output(metrics_dir, phase, line)
        pending += decoder.decode(b"", final=True)
        record_output(metrics_dir, phase, pending)
        exit_code = process.wait()
        return exit_code
    finally:
        stop.set()
        monitor.join(timeout=interval + 15)
        emit(events, "phase_end", phase=phase, exit_code=exit_code,
             wall_seconds=round(time.monotonic() - started, 3))


def cu_snapshot(metrics_dir: Path, label: str) -> None:
    usage = command_output(["colab", "usage"], timeout=30)
    raw = usage.get("stdout", "")
    matches = {
        "balance_cu": re.search(r"Current balance:\s*([\d.]+)", raw),
        "rate_cu_per_hour": re.search(r"Usage rate:\s*([\d.]+)/hr", raw),
        "active_assignments": re.search(r"Active assignments:\s*(\d+)", raw),
    }
    record = {
        "label": label,
        "exit_code": usage.get("exit_code"),
        "balance_cu": float(matches["balance_cu"].group(1)) if matches["balance_cu"] else None,
        "rate_cu_per_hour": float(matches["rate_cu_per_hour"].group(1)) if matches["rate_cu_per_hour"] else None,
        "active_assignments": int(matches["active_assignments"].group(1)) if matches["active_assignments"] else None,
        "raw": raw,
        "error": usage.get("stderr") or usage.get("error"),
    }
    emit(metrics_dir / "cu-snapshots.jsonl", "cu_snapshot", **record)
    print(json.dumps(record, ensure_ascii=False), flush=True)
    if record["balance_cu"] is None:
        raise RuntimeError(f"could not read Colab CU usage: {usage}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check_nodes(metrics_dir: Path, workflow_path: Path, base_url: str) -> None:
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    required = sorted({node["class_type"] for node in workflow.values()})
    with urllib.request.urlopen(f"{base_url}/object_info", timeout=30) as response:
        available = json.load(response)
    with urllib.request.urlopen(f"{base_url}/system_stats", timeout=20) as response:
        write_json(metrics_dir / "system_stats-ready.json", json.load(response))
    missing = sorted(set(required) - set(available))
    record = {"at_utc": utc_now(), "workflow_path": str(workflow_path),
              "required_count": len(required), "required": required, "missing": missing}
    write_json(metrics_dir / "node-check.json", record)
    emit(metrics_dir / "events.jsonl", "node_check", required_count=len(required), missing=missing)
    print(json.dumps(record, ensure_ascii=False), flush=True)
    if missing:
        raise RuntimeError(f"required ComfyUI nodes missing: {missing}")


def capture_comfy(metrics_dir: Path, results_dir: Path, base_url: str) -> None:
    batch = results_dir / "batch.json"
    records = json.loads(batch.read_text(encoding="utf-8")) if batch.exists() else []
    for name, url in (("system_stats.json", f"{base_url}/system_stats"),):
        with urllib.request.urlopen(url, timeout=20) as response:
            write_json(metrics_dir / name, json.load(response))
    for record in records:
        prompt_id = record.get("prompt_id")
        if prompt_id:
            with urllib.request.urlopen(f"{base_url}/history/{prompt_id}", timeout=20) as response:
                write_json(metrics_dir / f"history-{prompt_id}.json", json.load(response))
    log = Path("/content/h3-rental/ComfyUI/comfyUI-h3.log")
    if log.is_file():
        shutil.copy2(log, metrics_dir / "comfyUI-h3.log")
    artifacts = []
    for path in sorted(results_dir.rglob("*")):
        if path.is_file():
            artifacts.append({"path": str(path.relative_to(results_dir)), "bytes": path.stat().st_size,
                              "sha256": sha256(path)})
    write_json(metrics_dir / "u02-artifacts.json", artifacts)
    emit(metrics_dir / "events.jsonl", "comfy_capture", prompts=len(records), artifacts=len(artifacts))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics-dir", type=Path, required=True)
    actions = parser.add_subparsers(dest="action", required=True)
    env_parser = actions.add_parser("snapshot")
    env_parser.add_argument("--python", default=sys.executable)
    env_parser.add_argument("--label", required=True)
    cu_parser = actions.add_parser("cu")
    cu_parser.add_argument("label")
    run_parser = actions.add_parser("run")
    run_parser.add_argument("phase")
    run_parser.add_argument("--interval", type=float, default=5.0)
    run_parser.add_argument("command", nargs=argparse.REMAINDER)
    capture_parser = actions.add_parser("capture")
    capture_parser.add_argument("--results-dir", type=Path, default=Path("/content/h3-u02-results"))
    capture_parser.add_argument("--base-url", default="http://127.0.0.1:8188")
    node_parser = actions.add_parser("check-nodes")
    node_parser.add_argument("--workflow", type=Path, default=Path(
        "/content/h3-runner/templates/yz_h3_ep_unit/workflow_api.json"))
    node_parser.add_argument("--base-url", default="http://127.0.0.1:8188")
    args = parser.parse_args()
    if args.action == "snapshot":
        snapshot(args.metrics_dir, args.python, args.label)
    elif args.action == "cu":
        cu_snapshot(args.metrics_dir, args.label)
    elif args.action == "run":
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        return run_phase(args.metrics_dir, args.phase, args.interval, command)
    elif args.action == "check-nodes":
        check_nodes(args.metrics_dir, args.workflow, args.base_url)
    else:
        capture_comfy(args.metrics_dir, args.results_dir, args.base_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
