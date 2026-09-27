"""Offline checks for the A100 attention A/B comparison contract."""

import copy
import hashlib
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
from h3_a100_ab_contract import (graphs_match_except_candidate,
                                  graphs_match_except_output_prefix,
                                  parse_step_timing, timing_pair_passes,
                                  warmup_graphs_match_except_latent_prefix)
from colab_h3_a100_ab_host import (ColabTransportLost, admit_next,
                                   phase_receipt_status, run)
import colab_h3_a100_ab_host as host
import h3_a100_ab_phase as phase


def baseline_graph():
    return {
        "128": {"inputs": {"model": ["192", 0]}},
        "264": {"inputs": {"filename_prefix": "EP04-U02-v16-pass1-ab-b1"}},
        "400": {"inputs": {"filename_prefix": "h3_context/ep04_u02_ab_b1"}},
        "289": {"inputs": {"step": 12}},
    }


def test_graph_comparison_allows_only_attention_and_output_prefixes():
    baseline = baseline_graph()
    candidate = copy.deepcopy(baseline)
    candidate["58"] = {"class_type": "MiniMaxH3MemoryEfficientSageAttentionPatch",
                       "inputs": {"model": ["192", 0]}}
    candidate["128"]["inputs"]["model"] = ["58", 0]
    candidate["264"]["inputs"]["filename_prefix"] = "EP04-U02-v16-pass1-ab-c1"
    candidate["400"]["inputs"]["filename_prefix"] = "h3_context/ep04_u02_ab_c1"
    assert graphs_match_except_candidate(baseline, candidate)
    candidate["289"]["inputs"]["step"] = 11
    assert not graphs_match_except_candidate(baseline, candidate)


def test_graph_comparison_rejects_unexpected_attention_patch():
    candidate = baseline_graph()
    candidate["58"] = {"class_type": "OtherPatch", "inputs": {"model": ["192", 0]}}
    candidate["128"]["inputs"]["model"] = ["58", 0]
    with pytest.raises(ValueError, match="unexpected candidate"):
        graphs_match_except_candidate(baseline_graph(), candidate)


def test_memory_policy_graph_allows_only_output_prefixes():
    baseline = baseline_graph()
    baseline["58"] = {"class_type": "MiniMaxH3MemoryEfficientSageAttentionPatch",
                      "inputs": {"model": ["192", 0]}}
    baseline["128"]["inputs"]["model"] = ["58", 0]
    candidate = copy.deepcopy(baseline)
    candidate["264"]["inputs"]["filename_prefix"] = "EP04-U02-v16-pass1-ab-m1"
    candidate["400"]["inputs"]["filename_prefix"] = "h3_context/ep04_u02_ab_m1"
    assert graphs_match_except_output_prefix(baseline, candidate)
    candidate["128"]["inputs"]["model"] = ["192", 0]
    assert not graphs_match_except_output_prefix(baseline, candidate)


def test_memory_warmup_graph_allows_only_latent_prefix():
    baseline = baseline_graph()
    baseline.pop("264")
    baseline["289"]["inputs"]["step"] = 1
    candidate = copy.deepcopy(baseline)
    candidate["400"]["inputs"]["filename_prefix"] = "h3_context/ep04_u02_ab_m0"
    assert warmup_graphs_match_except_latent_prefix(baseline, candidate)
    candidate["128"]["inputs"]["model"] = ["changed", 0]
    assert not warmup_graphs_match_except_latent_prefix(baseline, candidate)
    candidate["289"]["inputs"]["step"] = 2
    with pytest.raises(ValueError, match="one-step"):
        warmup_graphs_match_except_latent_prefix(baseline, candidate)


def test_step_timing_requires_all_twelve_completed_steps():
    log = "\r".join(f"{step}/12 [00:{step:02d}<00:00" for step in range(1, 13))
    timing = parse_step_timing(log)
    assert timing.elapsed_seconds == tuple(range(1, 13))
    assert timing.intervals_seconds == (1,) * 11
    with pytest.raises(ValueError, match="expected 12"):
        parse_step_timing(log.replace("12/12", "11/12"))


def test_step_timing_uses_first_completion_when_tqdm_reprints_previous_step():
    log = "\r".join(["1/12 [02:02<00:00", "1/12 [03:49<00:00",
                     *[f"{step}/12 [{3 + 2 * (step - 2):02d}:49<00:00"
                       for step in range(2, 13)]])
    timing = parse_step_timing(log)
    assert timing.elapsed_seconds[0] == 122
    assert timing.elapsed_seconds[1] == 229


def test_timing_screen_requires_both_sampler_and_server_gain():
    baseline = {"server_wall_s": 100, "sampler_wall_s": 90}
    assert timing_pair_passes(baseline, {"server_wall_s": 84, "sampler_wall_s": 75})
    assert not timing_pair_passes(baseline, {"server_wall_s": 90, "sampler_wall_s": 70})
    assert not timing_pair_passes(baseline, {"server_wall_s": 80, "sampler_wall_s": 80})


def test_cu_admission_requires_reserve_and_wall_time():
    state = {"balance": 100.0, "rate": 6.77, "active": 1.0}
    deadline = datetime.now(timezone.utc) + timedelta(hours=1)
    admit_next(state, 100.0, time.monotonic(), 20.0, deadline, 2400)
    with pytest.raises(RuntimeError, match="CU/deadline"):
        admit_next(state, 100.0, time.monotonic(), 5.0, deadline, 2400)


def test_first_pair_rejects_insufficient_gain_without_b2(tmp_path, monkeypatch):
    monkeypatch.setattr(phase, "CONTENT", tmp_path)
    for label, server, sampler in (("B1", 100, 90), ("C1", 90, 70)):
        folder = tmp_path / "h3-a100-ab" / label
        folder.mkdir(parents=True)
        (folder / "validation.json").write_text(json.dumps({"server_wall_s": server}))
        (folder / "steps.json").write_text(json.dumps({"sampler_wall_s": sampler}))
    with pytest.raises(RuntimeError, match="timing screen"):
        phase.screen("C1", tmp_path / "h3-a100-ab/C1")
    report = json.loads((tmp_path / "h3-a100-ab/C1/timing_screen.json").read_text())
    assert report["timing_screen_passes"] is False


def test_attention_log_gate_matches_selected_profile(tmp_path):
    log = tmp_path / "comfy.log"
    log.write_text("Using pytorch attention\n")
    phase.verify_attention_mode("B1", log)
    with pytest.raises(RuntimeError, match="attention patch state"):
        phase.verify_attention_mode("C1", log)
    log.write_text("Applying MiniMax H3 Memory Efficient Sage Attention Patch to all transformer blocks\n")
    phase.verify_attention_mode("C1", log)


def test_memory_mode_log_gate_uses_only_the_startup_flag(tmp_path):
    log = tmp_path / "comfy.log"
    log.write_text("Disabling smart memory management\n")
    phase.verify_memory_mode("S1", log)
    with pytest.raises(RuntimeError, match="smart-memory"):
        phase.verify_memory_mode("M1", log)
    log.write_text("dynamic VRAM loading\n")
    phase.verify_memory_mode("M1", log)


def write_memory_sample(root, label, server, sampler, digest="same"):
    folder = root / "h3-a100-ab" / label
    folder.mkdir(parents=True)
    (folder / "validation.json").write_text(json.dumps({
        "server_wall_s": server,
        "video": {"sha256": f"container-{label}",
                  "decoded_video_sha256": digest,
                  "decoded_audio_sha256": digest},
        "latent": {"sha256": digest}}))
    (folder / "steps.json").write_text(json.dumps({"sampler_wall_s": sampler}))
    (folder / "phase.json").write_text(json.dumps({
        "startup_sha256": hashlib.sha256(phase.MEMORY_START.read_bytes()).hexdigest()}))
    return folder


def test_memory_screen_requires_time_and_byte_identical_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(phase, "CONTENT", tmp_path)
    startup = tmp_path / "start.sh"
    startup.write_text("start")
    monkeypatch.setattr(phase, "MEMORY_START", startup)
    write_memory_sample(tmp_path, "S1", 1300, 1200)
    candidate = write_memory_sample(tmp_path, "M1", 1050, 950)
    phase.memory_screen("M1", candidate)
    report = json.loads((candidate / "memory_timing_screen.json").read_text())
    assert report["timing_screen_passes"] is True
    (candidate / "validation.json").write_text(json.dumps({
        "server_wall_s": 1050,
        "video": {"sha256": "container-M1",
                  "decoded_video_sha256": "changed",
                  "decoded_audio_sha256": "same"},
        "latent": {"sha256": "same"}}))
    with pytest.raises(RuntimeError, match="output-hash"):
        phase.memory_screen("M1", candidate)


def test_memory_second_pair_rejects_baseline_drift(tmp_path, monkeypatch):
    monkeypatch.setattr(phase, "CONTENT", tmp_path)
    startup = tmp_path / "start.sh"
    startup.write_text("start")
    monkeypatch.setattr(phase, "MEMORY_START", startup)
    write_memory_sample(tmp_path, "S1", 1300, 1200)
    write_memory_sample(tmp_path, "M1", 1050, 950)
    write_memory_sample(tmp_path, "S2", 1500, 1400)
    candidate = write_memory_sample(tmp_path, "M2", 1200, 1100)
    with pytest.raises(RuntimeError, match="stability gate"):
        phase.memory_screen("M2", candidate)
    report = json.loads((candidate / "memory_timing_screen.json").read_text())
    assert report["baseline_spread"] > 0.10


def test_host_command_fails_fast_on_lost_transport(tmp_path):
    command = [sys.executable, "-c",
               "import time; print('RuntimeError: Connection was lost.', flush=True); time.sleep(30)"]
    started = time.monotonic()
    with pytest.raises(ColabTransportLost):
        run(command, tmp_path / "lost.log", timeout=15, detect_lost_connection=True)
    assert time.monotonic() - started < 5
    assert "Connection was lost" in (tmp_path / "lost.log").read_text()


def test_host_command_does_not_wait_for_inherited_pipe_after_cli_exit(tmp_path):
    code = ("import subprocess,sys; "
            "subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']); "
            "print('RuntimeError: Connection was lost.',flush=True);sys.exit(1)")
    started = time.monotonic()
    with pytest.raises(ColabTransportLost):
        run([sys.executable, "-c", code], tmp_path / "inherited.log",
            timeout=15, detect_lost_connection=True)
    assert time.monotonic() - started < 7


def test_host_command_timeout_is_bounded(tmp_path):
    command = [sys.executable, "-c", "import time; time.sleep(30)"]
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="host command exceeded"):
        run(command, tmp_path / "timeout.log", timeout=1)
    assert time.monotonic() - started < 5


def test_phase_receipt_rejects_stale_or_wrong_label():
    attempted = datetime.now(timezone.utc)
    receipt = {"label": "C1", "started_at_utc": (attempted + timedelta(seconds=1)).isoformat(),
               "state": "success"}
    assert phase_receipt_status(receipt, "C1", attempted) == "success"
    assert phase_receipt_status(receipt, "B1", attempted) == "wrong_label"
    receipt["started_at_utc"] = (attempted - timedelta(seconds=1)).isoformat()
    assert phase_receipt_status(receipt, "C1", attempted) == "stale"


def test_watchdog_remains_alive_if_paid_assignment_is_not_confirmed_stopped(
        tmp_path, monkeypatch):
    calls = []

    class Watcher:
        def poll(self):
            return None

        def terminate(self):
            calls.append("terminated")

    monkeypatch.setattr(host, "run", lambda command, *args, **kwargs:
                        "active session" if command[1] == "sessions" else "")
    monkeypatch.setattr(host, "snapshot", lambda *args: {"active": 1, "rate": 6.77})
    with pytest.raises(RuntimeError, match="zero active"):
        host.stop_and_verify("test-session", tmp_path, Watcher())
    assert calls == []
