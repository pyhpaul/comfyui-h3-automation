"""Offline tests for the bounded, reversible attention probe."""

import contextlib
import gzip
import json
import sys
import types
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
import h3_a100_attention_probe as probe
import h3_a100_attention_probe_hook as hook
from h3_a100_profile_runtime import export_bounded_timeline


def archived_attention_excerpt():
    return ("import types\n"
            "def minimax_sageattn_forward(self, s, dtype, qkv):\n"
            "    if True:\n" + hook.ANCHOR + "\n")


def test_attention_hook_is_hash_guarded_and_reversible(tmp_path, monkeypatch):
    root = tmp_path / "ComfyUI"
    source = root / hook.RELATIVE_SOURCE
    source.parent.mkdir(parents=True)
    original = archived_attention_excerpt().encode()
    source.write_bytes(original)
    monkeypatch.setattr(hook, "EXPECTED_SHA256", hook.digest(original))
    backup = tmp_path / "backup"
    manifest = hook.install(root, backup)
    assert manifest["original_sha256"] == hook.digest(original)
    assert "probe_attention(qkv, dtype" in source.read_text()
    compile(source.read_text(), str(source), "exec")
    hook.restore(root, backup)
    assert source.read_bytes() == original


def test_attention_hook_rejects_unknown_source(tmp_path):
    source = tmp_path / hook.RELATIVE_SOURCE
    source.parent.mkdir(parents=True)
    source.write_text("import types\n")
    with pytest.raises(RuntimeError, match="differs"):
        hook.install(tmp_path, tmp_path / "backup")


def test_capture_budget_checks_all_memory_domains():
    metadata = [{"logical_bytes": 300 << 20}] * 3
    assert probe.capture_reason(metadata, 10 << 30, 7 << 30, 3 << 30) is None
    assert probe.capture_reason(metadata, 8 << 30, 7 << 30, 3 << 30) == "insufficient_gpu_margin"
    assert probe.capture_reason(metadata, 10 << 30, 5 << 30, 3 << 30) == "insufficient_ram_margin"
    assert probe.capture_reason(metadata, 10 << 30, 7 << 30, 1 << 30) == "insufficient_disk_margin"
    too_large = [{"logical_bytes": 600 << 20}] * 2
    assert probe.capture_reason(too_large, 20 << 30, 20 << 30, 20 << 30) == "capture_exceeds_1_gib"


def test_probe_records_pre_mutation_metadata_without_torch_sync(tmp_path, monkeypatch):
    fake_torch = types.SimpleNamespace(
        profiler=types.SimpleNamespace(record_function=lambda name: contextlib.nullcontext()))
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setenv("H3_ATTENTION_PROBE_OUTPUT", str(tmp_path))
    monkeypatch.delenv("H3_ATTENTION_CAPTURE", raising=False)
    monkeypatch.setattr(probe, "_call_count", 0)

    class Tensor:
        shape = (1, 2, 3, 4)
        dtype = "bf16"
        device = "cuda:0"

        def stride(self):
            return (24, 12, 4, 1)

        def numel(self):
            return 24

        def element_size(self):
            return 2

    qkv = [Tensor(), Tensor(), Tensor()]

    def call(values, dtype):
        values.clear()
        return dtype

    assert probe.probe_attention(qkv, "bf16", call) == "bf16"
    record = json.loads((tmp_path / "attention-calls.jsonl").read_text())
    assert record["capture_point"] == "before_in_place_k_mean"
    assert record["qkv"][0]["stride"] == [24, 12, 4, 1]
    for _ in range(9):
        probe.probe_attention([Tensor(), Tensor(), Tensor()], "bf16", call)
    assert len((tmp_path / "attention-calls.jsonl").read_text().splitlines()) == 8


def test_timeline_export_is_bounded_and_keeps_stream_identity(tmp_path, monkeypatch):
    event = types.SimpleNamespace(
        key="sageattention::kernel", time_range=types.SimpleNamespace(start=1, end=3),
        device_type="CUDA", device_index=0, device_resource_id=7, thread=4,
        id=1, cpu_parent=None, activity_type="kernel", is_async=True,
        is_user_annotation=False, linked_correlation_id=2, flow_id=3,
        flow_type=1, flow_start=False, external_id=4)
    captured = types.SimpleNamespace(events=lambda: [event])
    output = tmp_path / "timeline.json.gz"
    report = export_bounded_timeline(captured, output)
    assert report["available"] is True
    with gzip.open(output, "rt") as stream:
        recorded = json.load(stream)
    assert recorded["complete"] is True
    assert recorded["events"][0]["resource_id"] == 7
    assert recorded["events"][0]["linked_correlation_id"] == 2
    monkeypatch.setattr("h3_a100_profile_runtime.MAX_TIMELINE_BYTES", 5)
    limited = export_bounded_timeline(captured, tmp_path / "too-large.json.gz")
    assert limited["reason"] == "compressed_byte_limit"
    assert not (tmp_path / "too-large.json.gz").exists()


def test_complete_export_does_not_discard_at_old_50k_event_limit(tmp_path):
    event = types.SimpleNamespace(
        key="kernel", time_range=types.SimpleNamespace(start=1, end=2),
        device_type="CUDA", device_index=0, device_resource_id=7, thread=4,
        id=1, cpu_parent=None, activity_type="kernel", is_async=True,
        is_user_annotation=False, linked_correlation_id=2, flow_id=0,
        flow_type=0, flow_start=False, external_id=0)
    captured = types.SimpleNamespace(events=lambda: [event] * 50_001)
    output = tmp_path / "large-timeline.json.gz"
    report = export_bounded_timeline(captured, output)
    assert report["available"] is True
    with gzip.open(output, "rt") as stream:
        recorded = json.load(stream)
    assert recorded["event_count"] == 50_001
    assert len(recorded["events"]) == 50_001
