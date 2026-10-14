"""Bounded, prompt-window RTX 5090 sensor capture; never touches ComfyUI."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


QUERY = "uuid,index,utilization.gpu,memory.used"
MAX_DURATION_S = 2700
MAX_QUERY_S = 2.5


def sample_gpu(run_id: str, process_pid: int, gpu_uuid: str,
               device_index: int, query_timeout_s: float) -> dict[str, object]:
    result = subprocess.run(
        ["nvidia-smi", f"--query-gpu={QUERY}", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=query_timeout_s, check=True)
    rows = [row.strip() for row in result.stdout.splitlines() if row.strip()]
    if len(rows) != 1:
        raise ValueError("expected exactly one GPU sensor row")
    fields = [field.strip() for field in rows[0].split(",")]
    if len(fields) != 4 or fields[0] != gpu_uuid or int(fields[1]) != device_index:
        raise ValueError("GPU sensor identity differs from admitted device")
    return {"at_utc": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id, "process_pid": process_pid,
            "gpu_uuid": gpu_uuid, "device_index": device_index,
            "utilization_pct": int(fields[2]), "vram_mib": int(fields[3])}


def process_start_ticks(pid: int) -> int:
    raw = Path(f"/proc/{pid}/stat").read_text()
    return int(raw.rsplit(") ", 1)[1].split()[19])


def capture(output: Path, stop_file: Path, run_id: str, process_pid: int,
            gpu_uuid: str, device_index: int, interval_s: float,
            duration_s: float) -> bool:
    if not run_id or process_pid <= 0 or not gpu_uuid or device_index < 0 \
            or not 0 < interval_s <= 5 or not 0 < duration_s <= MAX_DURATION_S \
            or output.resolve() == stop_file.resolve() \
            or output.exists() or stop_file.exists():
        raise ValueError("invalid or reused telemetry capture boundary")
    deadline = time.monotonic() + duration_s
    next_due = time.monotonic()
    start_ticks = process_start_ticks(process_pid)
    previous_sample_at: float | None = None
    with output.open("x", encoding="utf-8") as stream:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            if process_start_ticks(process_pid) != start_ticks:
                raise ValueError("target process identity changed during telemetry")
            sample = sample_gpu(run_id, process_pid, gpu_uuid, device_index,
                                min(MAX_QUERY_S, remaining))
            sampled_at = time.monotonic()
            if sampled_at > deadline:
                return False
            if previous_sample_at is not None and sampled_at - previous_sample_at > 7.5:
                raise TimeoutError("GPU sampling gap exceeds evidence limit")
            previous_sample_at = sampled_at
            if process_start_ticks(process_pid) != start_ticks:
                raise ValueError("target process identity changed during telemetry")
            sample["process_start_ticks"] = start_ticks
            stream.write(json.dumps(sample) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            if stop_file.exists():
                return True
            next_due += interval_s
            now = time.monotonic()
            if now > next_due:
                raise TimeoutError("GPU sampling exceeded fixed cadence")
            time.sleep(min(next_due - now, max(0, deadline - now)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stop-file", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--process-pid", type=int, required=True)
    parser.add_argument("--gpu-uuid", required=True)
    parser.add_argument("--device-index", type=int, required=True)
    parser.add_argument("--interval-s", type=float, default=5)
    parser.add_argument("--duration-s", type=float, default=2700)
    args = parser.parse_args()
    stopped = capture(args.output, args.stop_file, args.run_id, args.process_pid,
                      args.gpu_uuid, args.device_index, args.interval_s,
                      args.duration_s)
    return 0 if stopped else 2


if __name__ == "__main__":
    raise SystemExit(main())
