"""Synthetic cross-stream and causal-uncertainty cases for the offline gate."""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
from h3_a100_trace_analysis import SCHEMA, analyze_timeline


def event(name, start, end, device="CPU", stream=None, link=0, flow=0):
    return {"name": name, "start_us": start, "end_us": end,
            "device_type": device, "resource_id": stream,
            "linked_correlation_id": link, "flow_id": flow}


def trace(*items):
    return {"schema": SCHEMA, "complete": True,
            "event_count": len(items), "events": list(items)}


def test_overlapping_streams_use_union_not_sum():
    result = analyze_timeline(trace(
        event("h3_sampler_interval", 0, 100),
        event("h3_sage_wrapper", 10, 90),
        event("kernel-a", 10, 50, "DeviceType.CUDA", 1),
        event("kernel-b", 40, 80, "DeviceType.CUDA", 2)))
    assert result["gpu_busy_in_helper_union_us"] == 70
    assert result["unknown_possible_upper_us"] == 10
    assert result["cross_stream_count"] == 2
    assert result["classification"] == "no_launch_candidate"


def test_queued_kernel_is_not_counted_running_or_qualified_launch():
    result = analyze_timeline(trace(
        event("h3_sampler_interval", 0, 100),
        event("h3_sage_wrapper", 0, 100),
        event("kernel-a", 0, 20, "CUDA", 1),
        event("cudaLaunchKernel", 21, 22, "CPU", link=4),
        event("kernel-b", 40, 50, "CUDA", 1, link=4)))
    assert result["unknown_possible_upper_us"] == 70
    assert result["qualified_gap_lower_us"] == 0
    assert result["classification"] == "inconclusive"


def test_copy_sync_dependency_and_missing_link_stay_unknown():
    result = analyze_timeline(trace(
        event("h3_sampler_interval", 0, 100),
        event("h3_sage_wrapper", 0, 100),
        event("cudaStreamSynchronize", 1, 30),
        event("cudaMemcpyAsync", 30, 50, "CUDA", 2, flow=7),
        event("kernel-without-link", 50, 70, "CUDA", 1)))
    assert result["sync_event_count"] == 1
    assert result["copy_event_count"] == 1
    assert result["flow_event_count"] == 1
    assert result["linked_event_count"] == 0
    assert result["qualified_gap_lower_us"] == 0
    assert result["unknown_possible_upper_us"] == 60


def test_missing_or_truncated_trace_cannot_pass():
    base = trace(event("h3_sampler_interval", 0, 100),
                 event("h3_sage_wrapper", 0, 100),
                 event("kernel", 0, 100, "CUDA", 1))
    assert analyze_timeline({**base, "complete": False})["classification"] == "inconclusive"
    assert analyze_timeline({**base, "event_count": 4})["classification"] == "inconclusive"
    assert analyze_timeline({**base, "events": base["events"][1:]})["classification"] == "inconclusive"
