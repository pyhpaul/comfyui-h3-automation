"""Offline gates for the single-session A100 diagnostic and memory trial."""

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
import colab_h3_a100_combined_host as combined


def test_combined_host_never_assigns_gpu_without_explicit_paid_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["combined", "--max-cu", "20"])
    monkeypatch.setattr(combined, "require_combined_inputs",
                        lambda: pytest.fail("must not inspect paid inputs"))
    with pytest.raises(ValueError, match="--execute-paid"):
        combined.main()


def test_combined_phase_dispatch_and_unique_receipts(tmp_path, monkeypatch):
    calls = []
    state = {"balance": 100.0, "active": 1.0, "rate": 6.77}
    monkeypatch.setattr(combined, "snapshot", lambda *args: state)
    monkeypatch.setattr(combined, "admit_next", lambda *args: None)
    monkeypatch.setattr(combined, "exec_file",
                        lambda session, path, timeout, log, **kwargs:
                        calls.append((path.name, timeout, kwargs)))
    deadline = datetime.now(timezone.utc) + timedelta(hours=3)
    remote = "h3drive_h3:bucket/profile-h3-a100-combined-unique"
    for label in ("P_B", "P_C", "M0", "S1", "M1"):
        combined.run_checked_phase("session", label, remote, tmp_path, tmp_path / "cu.jsonl",
                                   state, time.monotonic(), 20, deadline, 6.77)
    assert [call[0] for call in calls] == ["h3_a100_profile_phase.py"] * 3 + [
        "h3_a100_ab_phase.py"] * 2
    assert calls[2][2]["H3_DISABLE_SMART_MEMORY"] == "0"
    assert calls[3][2]["H3_AB_RUN"] == "S1"
    assert calls[4][2]["receipt_path"] == remote + "/M1/phase.json"


def test_combined_memory_safety_rejects_high_peak(monkeypatch):
    report = {"kind": "instrumented_one_step_not_timing_sample",
              "gpu": "NVIDIA A100-SXM4-80GB", "peak_reserved_bytes": 30 * 1024 ** 3}

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, stdout=json.dumps(report))

    monkeypatch.setattr(combined.subprocess, "run", fake_run)
    combined.check_memory_profile("h3drive_h3:bucket/profile-unique")
    report["peak_reserved_bytes"] = 71 * 1024 ** 3
    with pytest.raises(RuntimeError, match="70 GiB"):
        combined.check_memory_profile("h3drive_h3:bucket/profile-unique")


def test_combined_profile_modes_share_startup_script(monkeypatch):
    receipts = {label: {"label": label, "state": "success",
                        "startup_sha256": "same-startup",
                        "disable_smart_memory": "0" if label == "M0" else "1"}
                for label in combined.PROFILE_LABELS}

    def fake_run(command, **kwargs):
        label = command[2].split("/")[-2]
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(receipts[label]))

    monkeypatch.setattr(combined.subprocess, "run", fake_run)
    combined.check_profile_startup_contract("h3drive_h3:bucket/profile-unique")
    receipts["M0"]["startup_sha256"] = "different"
    with pytest.raises(RuntimeError, match="differs beyond"):
        combined.check_profile_startup_contract("h3drive_h3:bucket/profile-unique")
