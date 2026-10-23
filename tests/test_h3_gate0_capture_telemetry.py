"""Offline sensor capture tests; no GPU or ComfyUI connection."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
import h3_gate0_capture_telemetry as telemetry


def test_capture_writes_bound_sample_and_refuses_reuse(tmp_path, monkeypatch):
    seen = []

    def fake_run(command, **kwargs):
        seen.append(command)
        return subprocess.CompletedProcess(command, 0, "GPU-fixture, 0, 37, 1234\n", "")

    monkeypatch.setattr(telemetry.subprocess, "run", fake_run)
    monkeypatch.setattr(telemetry, "process_start_ticks", lambda pid: 999)
    output = tmp_path / "gpu.jsonl"
    stop = tmp_path / "stop"
    stop.touch()
    with pytest.raises(ValueError, match="reused"):
        telemetry.capture(output, stop, "run-1", 123, "GPU-fixture", 0, 5, 30)
    stop.unlink()
    monkeypatch.setattr(telemetry.time, "sleep", lambda _: stop.touch())
    assert telemetry.capture(output, stop, "run-1", 123, "GPU-fixture", 0, 5, 30)
    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(records) == 2
    assert all(record["run_id"] == "run-1" and record["process_pid"] == 123
               and record["gpu_uuid"] == "GPU-fixture"
               and record["device_index"] == 0 for record in records)
    assert records[-1]["utilization_pct"] == 37
    assert records[-1]["vram_mib"] == 1234
    assert len(seen) == 2
    with pytest.raises(ValueError, match="reused"):
        telemetry.capture(output, stop, "run-1", 123, "GPU-fixture", 0, 5, 30)


def test_wrong_gpu_identity_is_rejected(monkeypatch):
    monkeypatch.setattr(telemetry.subprocess, "run", lambda command, **kwargs:
                        subprocess.CompletedProcess(command, 0, "GPU-other, 0, 0, 100\n", ""))
    with pytest.raises(ValueError, match="identity"):
        telemetry.sample_gpu("run-1", 123, "GPU-fixture", 0, 2.5)


def test_slow_query_and_changed_process_stop_capture(tmp_path, monkeypatch):
    monkeypatch.setattr(telemetry, "process_start_ticks", lambda pid: 999)

    def slow_sample(*args):
        telemetry.time.sleep(0.02)
        return {"at_utc": "2026-09-27T00:00:00+00:00"}

    monkeypatch.setattr(telemetry, "sample_gpu", slow_sample)
    with pytest.raises(TimeoutError, match="fixed cadence"):
        telemetry.capture(tmp_path / "slow.jsonl", tmp_path / "stop", "run-1",
                          123, "GPU-fixture", 0, 0.005, 1)

    state = {"ticks": 0}

    def changing_ticks(pid):
        state["ticks"] += 1
        return 999 if state["ticks"] < 3 else 1000

    monkeypatch.setattr(telemetry, "process_start_ticks", changing_ticks)
    with pytest.raises(ValueError, match="identity changed"):
        telemetry.capture(tmp_path / "changed.jsonl", tmp_path / "other-stop",
                          "run-1", 123, "GPU-fixture", 0, 5, 1)


def test_duration_cap_and_same_stop_path_rejected(tmp_path):
    output = tmp_path / "gpu.jsonl"
    with pytest.raises(ValueError, match="boundary"):
        telemetry.capture(output, output, "run-1", 123, "GPU-fixture", 0, 5, 30)
    with pytest.raises(ValueError, match="boundary"):
        telemetry.capture(output, tmp_path / "stop", "run-1", 123,
                          "GPU-fixture", 0, 5, 2701)


def test_deadline_does_not_start_another_query(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(telemetry, "process_start_ticks", lambda pid: 999)

    def slow_sample(*args):
        calls.append(args)
        telemetry.time.sleep(0.02)
        return {"at_utc": "2026-09-27T00:00:00+00:00"}

    monkeypatch.setattr(telemetry, "sample_gpu", slow_sample)
    assert not telemetry.capture(tmp_path / "gpu.jsonl", tmp_path / "stop", "run-1",
                                 123, "GPU-fixture", 0, 0.005, 0.001)
    assert len(calls) == 1
