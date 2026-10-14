"""Verify raw GPU sample identity and coverage without claiming sensor truth."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any


def _utc(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("telemetry timestamp is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("telemetry timestamp has no timezone")
    return parsed


def verify_telemetry(path: Path, gpu_uuid: str, device_index: int,
                     started_at_utc: str, finished_at_utc: str,
                     *, run_id: str | None = None,
                     process_pid: int | None = None) -> dict[str, Any]:
    raw = path.read_bytes()
    samples = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    if len(samples) < 2 or not isinstance(gpu_uuid, str) or not gpu_uuid \
            or isinstance(device_index, bool) or not isinstance(device_index, int) \
            or device_index < 0:
        raise ValueError("telemetry identity or samples are missing")
    start = _utc(started_at_utc)
    finish = _utc(finished_at_utc)
    times = []
    for sample in samples:
        if not isinstance(sample, dict):
            raise ValueError("telemetry sample is not an object")
        if sample.get("gpu_uuid") != gpu_uuid or sample.get("device_index") != device_index:
            raise ValueError("GPU UUID or device index differs")
        if run_id is not None and sample.get("run_id") != run_id:
            raise ValueError("telemetry run ID differs")
        if process_pid is not None and sample.get("process_pid") != process_pid:
            raise ValueError("telemetry process PID differs")
        utilization = sample.get("utilization_pct")
        vram = sample.get("vram_mib")
        if isinstance(utilization, bool) or isinstance(vram, bool) \
                or not isinstance(utilization, (int, float)) \
                or not isinstance(vram, (int, float)) \
                or not math.isfinite(utilization) or not math.isfinite(vram) \
                or not 0 <= utilization <= 100 or vram < 0:
            raise ValueError("GPU sensor reading is malformed")
        times.append(_utc(sample.get("at_utc")))
    if not start < finish or abs((times[0] - start).total_seconds()) > 7.5 \
            or abs((finish - times[-1]).total_seconds()) > 7.5 \
            or any(not 0 < (right - left).total_seconds() <= 7.5
                   for left, right in zip(times, times[1:])):
        raise ValueError("telemetry does not cover the prompt at expected cadence")
    return {"raw_sha256": {"tier": "derived_verified", "value": hashlib.sha256(raw).hexdigest()},
            "gpu_uuid": {"tier": "derived_verified", "value": gpu_uuid},
            "device_index": {"tier": "derived_verified", "value": device_index},
            "coverage": {"tier": "derived_verified", "samples": len(samples)},
            "sensor_values": {"tier": "reported_only"}}
