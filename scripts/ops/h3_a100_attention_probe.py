"""Bounded metadata and optional real-input capture for the H3 Sage wrapper."""

from __future__ import annotations

import json
import os
import shutil
import threading
from pathlib import Path
from typing import Callable, TypeVar


T = TypeVar("T")
MAX_CALL_RECORDS = 8
MAX_CAPTURE_BYTES = 1 << 30
CAPTURE_CALL_INDEX = 1
_lock = threading.Lock()
_call_count = 0


def tensor_metadata(tensor: object) -> dict[str, object]:
    return {"shape": list(tensor.shape), "stride": list(tensor.stride()),
            "dtype": str(tensor.dtype), "device": str(tensor.device),
            "logical_bytes": tensor.numel() * tensor.element_size()}


def available_ram_bytes() -> int:
    available = None
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            available = int(line.split()[1]) * 1024
            break
    if available is None:
        raise RuntimeError("MemAvailable is unavailable")
    limit = Path("/sys/fs/cgroup/memory.max")
    current = Path("/sys/fs/cgroup/memory.current")
    if limit.is_file() and current.is_file():
        maximum = limit.read_text().strip()
        if maximum != "max":
            available = min(available, max(0, int(maximum) - int(current.read_text())))
    return available


def capture_reason(metadata: list[dict[str, object]], gpu_free: int,
                   ram_free: int, disk_free: int) -> str | None:
    sizes = [int(item["logical_bytes"]) for item in metadata]
    total = sum(sizes)
    if total > MAX_CAPTURE_BYTES:
        return "capture_exceeds_1_gib"
    if gpu_free < max(sizes) + 8 * (1 << 30):
        return "insufficient_gpu_margin"
    if ram_free < total * 2 + 4 * (1 << 30):
        return "insufficient_ram_margin"
    if disk_free < total + 1 * (1 << 30):
        return "insufficient_disk_margin"
    return None


def probe_attention(qkv: list, dtype: object, call: Callable[..., T]) -> T:
    global _call_count
    with _lock:
        index = _call_count
        _call_count += 1
    import torch

    if index >= MAX_CALL_RECORDS:
        with torch.profiler.record_function("h3_sage_wrapper"):
            return call(qkv, dtype)

    output = Path(os.environ["H3_ATTENTION_PROBE_OUTPUT"])
    output.mkdir(parents=True, exist_ok=True)
    metadata = [tensor_metadata(item) for item in qkv]
    record: dict[str, object] = {"call_index": index, "qkv": metadata,
                                 "output_dtype": str(dtype),
                                 "capture_point": "before_in_place_k_mean"}
    captured = None
    if index == CAPTURE_CALL_INDEX and os.environ.get("H3_ATTENTION_CAPTURE") == "1":
        gpu_free, _ = torch.cuda.mem_get_info()
        reason = capture_reason(metadata, gpu_free, available_ram_bytes(),
                                shutil.disk_usage(output).free)
        record["capture_status"] = reason or "captured"
        if reason is None:
            with torch.profiler.record_function("h3_probe_capture_copy_excluded"):
                captured = [item.detach().to("cpu", copy=True).contiguous() for item in qkv]
    with torch.profiler.record_function("h3_probe_metadata_excluded"):
        with (output / "attention-calls.jsonl").open("a") as stream:
            stream.write(json.dumps(record) + "\n")
    with torch.profiler.record_function("h3_sage_wrapper"):
        result = call(qkv, dtype)
    if captured is not None:
        capture_path = output / "representative-qkv.pt"
        if capture_path.exists():
            raise RuntimeError("representative QKV capture already exists")
        with torch.profiler.record_function("h3_probe_capture_save_excluded"):
            torch.save({"qkv": captured, "metadata": metadata}, capture_path)
        if capture_path.stat().st_size > MAX_CAPTURE_BYTES:
            capture_path.unlink()
            raise RuntimeError("serialized QKV exceeded the 1 GiB capture limit")
    return result
