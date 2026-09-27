"""Conservative interval bounds for the one-step Sage helper launch question.

This cannot prove CUDA dependency readiness from FunctionEvent records alone.
The lower bound is therefore zero; only a small upper bound can close the branch.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path


SCHEMA = "torch-2.14-function-event-v1"


def _union(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _duration(intervals: list[tuple[float, float]]) -> float:
    return sum(end - start for start, end in _union(intervals))


def _overlap(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return max(a[0], b[0]), min(a[1], b[1])


def _range(event: dict[str, object]) -> tuple[float, float]:
    start, end = float(event["start_us"]), float(event["end_us"])
    if start < 0 or end < start:
        raise ValueError("invalid event interval")
    return start, end


def analyze_timeline(trace: dict[str, object]) -> dict[str, object]:
    events = trace.get("events")
    if (trace.get("schema") != SCHEMA or trace.get("complete") is not True
            or not isinstance(events, list) or trace.get("event_count") != len(events)):
        return {"classification": "inconclusive", "reason": "incomplete_or_unknown_schema"}
    try:
        sampler = [event for event in events if event["name"] == "h3_sampler_interval"]
        if len(sampler) != 1:
            raise ValueError("missing_or_multiple_sampler_markers")
        sampler_range = _range(sampler[0])
        sampler_us = sampler_range[1] - sampler_range[0]
        if sampler_us <= 0:
            raise ValueError("empty_sampler_marker")
        helpers = _union([_overlap(_range(event), sampler_range) for event in events
                          if event["name"] == "h3_sage_wrapper"])
        if not helpers:
            raise ValueError("missing_sage_helper_markers")
        gpu = [_range(event) for event in events
               if str(event["device_type"]).upper().endswith("CUDA")]
        if not gpu:
            raise ValueError("missing_cuda_events")
        _ = [_range(event) for event in events]
    except (KeyError, TypeError, ValueError) as exc:
        return {"classification": "inconclusive", "reason": str(exc)}

    helper_us = _duration(helpers)
    busy_in_helper = _duration([_overlap(work, helper) for work in gpu
                                for helper in helpers])
    possible_us = max(0.0, helper_us - busy_in_helper)
    upper_fraction = min(1.0, possible_us / sampler_us)
    names = [str(event["name"]).lower() for event in events]
    return {
        "classification": "no_launch_candidate" if upper_fraction < 0.15 else "inconclusive",
        "reason": "FunctionEvent lacks a complete dependency-ready signal",
        "sampler_us": sampler_us,
        "sage_helper_union_us": helper_us,
        "gpu_busy_in_helper_union_us": busy_in_helper,
        "qualified_gap_lower_us": 0.0,
        "unknown_possible_upper_us": possible_us,
        "qualified_gap_lower_fraction": 0.0,
        "unknown_possible_upper_fraction": upper_fraction,
        "cuda_event_count": len(gpu),
        "copy_event_count": sum("copy" in name or "memcpy" in name for name in names),
        "sync_event_count": sum("synchroniz" in name or "streamwait" in name
                                for name in names),
        "linked_event_count": sum(bool(event.get("linked_correlation_id"))
                                  for event in events),
        "flow_event_count": sum(bool(event.get("flow_id")) for event in events),
        "cross_stream_count": len({event.get("resource_id") for event in events
                                   if str(event["device_type"]).upper().endswith("CUDA")}),
    }


def analyze_file(path: Path) -> dict[str, object]:
    with gzip.open(path, "rt") as stream:
        return analyze_timeline(json.load(stream))
