"""One-shot PyTorch profiler around the H3 sampler, not a timing sample."""

from __future__ import annotations

import gzip
import json
import os
import time
from pathlib import Path
from typing import Callable, TypeVar

from h3_a100_trace_analysis import analyze_file


T = TypeVar("T")
MAX_TIMELINE_BYTES = 32 * 1024 * 1024
TIMELINE_SCHEMA = "torch-2.14-function-event-v1"


def _device_time_us(item: object) -> float:
    return float(getattr(item, "self_device_time_total",
                         getattr(item, "self_cuda_time_total", 0.0)))


def _event_record(item: object) -> dict[str, object]:
    parent = item.cpu_parent
    return {"id": item.id, "name": item.key,
            "start_us": float(item.time_range.start),
            "end_us": float(item.time_range.end),
            "device_type": str(item.device_type),
            "device_index": item.device_index,
            "resource_id": item.device_resource_id,
            "thread": item.thread, "activity_type": item.activity_type,
            "is_async": item.is_async, "is_user_annotation": item.is_user_annotation,
            "parent_id": parent.id if parent is not None else None,
            "linked_correlation_id": item.linked_correlation_id,
            "flow_id": item.flow_id, "flow_type": item.flow_type,
            "flow_start": item.flow_start, "external_id": item.external_id}


def export_bounded_timeline(captured: object, output: Path) -> dict[str, object]:
    events = captured.events()
    temporary = output.with_name(output.name + ".tmp")
    try:
        with temporary.open("wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as zipped:
                zipped.write((json.dumps({"kind": "complete_one_step_timeline",
                                          "schema": TIMELINE_SCHEMA,
                                          "complete": True,
                                          "event_count": len(events)},
                                         separators=(",", ":"))[:-1] + ',"events":[').encode())
                for index, item in enumerate(events):
                    if index:
                        zipped.write(b",")
                    zipped.write(json.dumps(_event_record(item), separators=(",", ":")).encode())
                    if index % 1000 == 0:
                        zipped.flush()
                        if raw.tell() > MAX_TIMELINE_BYTES:
                            return {"available": False, "reason": "compressed_byte_limit",
                                    "event_count": len(events), "serialized_events": index + 1}
                zipped.write(b"]}\n")
        if temporary.stat().st_size > MAX_TIMELINE_BYTES:
            return {"available": False, "reason": "compressed_byte_limit",
                    "event_count": len(events)}
        temporary.replace(output)
    except (AttributeError, TypeError, ValueError, OSError) as exc:
        return {"available": False, "reason": f"unsupported_event_schema:{type(exc).__name__}",
                "event_count": len(events)}
    finally:
        temporary.unlink(missing_ok=True)
    return {"available": True, "complete": True, "event_count": len(events),
            "compressed_bytes": output.stat().st_size, "path": str(output),
            "schema": TIMELINE_SCHEMA}


def profile_sampler(call: Callable[[], T]) -> T:
    output = Path(os.environ["H3_PROFILE_OUTPUT"])
    if output.exists():
        raise RuntimeError(f"profiler output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    import torch
    from torch.profiler import ProfilerActivity, profile, record_function

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA profiler requires the assigned A100")
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    started = time.monotonic()
    with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA],
                 record_shapes=False, profile_memory=True, with_stack=False) as captured:
        with record_function("h3_sampler_interval"):
            result = call()
            torch.cuda.synchronize()
    wall_s = time.monotonic() - started

    events = sorted(captured.key_averages(), key=_device_time_us, reverse=True)
    def summarize(item: object) -> dict[str, object]:
        return {"name": item.key, "count": item.count,
                "self_device_ms": round(_device_time_us(item) / 1000, 3),
                "cpu_total_ms": round(float(item.cpu_time_total) / 1000, 3),
                "device_total_ms": round(float(getattr(item, "device_time_total", 0.0)) / 1000, 3)}

    top = [summarize(item) for item in events[:100]]
    transfer_terms = ("memcpy", "copy_", "_to_copy", "aten::to")
    transfer_events = [item for item in events if any(term in item.key.lower()
                                                      for term in transfer_terms)]
    report = {"kind": "instrumented_one_step_not_timing_sample",
              "wall_s": round(wall_s, 3), "torch": torch.__version__,
              "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0),
              "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
              "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
              "event_count": len(events), "top_self_device": top,
              "sampler_interval_source": "h3_sampler_interval trace marker",
              "transfer_event_count": len(transfer_events),
              "transfer_named_self_device_ms": round(sum(_device_time_us(item)
                                                         for item in transfer_events) / 1000, 3),
              "top_transfer_events": [summarize(item) for item in transfer_events[:50]]}
    if os.environ.get("H3_PROFILE_TIMELINE_OUTPUT"):
        report["timeline"] = export_bounded_timeline(
            captured, Path(os.environ["H3_PROFILE_TIMELINE_OUTPUT"]))
        if report["timeline"]["available"]:
            try:
                report["launch_gap_bounds"] = analyze_file(
                    Path(os.environ["H3_PROFILE_TIMELINE_OUTPUT"]))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                report["launch_gap_bounds"] = {
                    "classification": "inconclusive",
                    "reason": f"trace_analysis_failed:{type(exc).__name__}"}
    output.write_text(json.dumps(report, indent=2) + "\n")
    return result
