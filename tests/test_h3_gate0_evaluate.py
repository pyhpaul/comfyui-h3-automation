"""Raw-artifact gate decisions; media decoders are stubbed only in unit fixtures."""

import copy
import hashlib
import json
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
import h3_gate0_evaluate as gate
from h3_gate0_outputs import prefix_baseline


RUN = "run-fixture"
PROMPT = "prompt-fixture"
CLIENT = "11111111-1111-4111-8111-111111111111"
ATTEMPT = "22222222-2222-4222-8222-222222222222"


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path


def _graph():
    return {
        "58": {"class_type": "MiniMaxH3MemoryEfficientSageAttentionPatch",
               "inputs": {"model": ["192", 0]}},
        "128": {"inputs": {"model": ["58", 0]}},
        "192": {"inputs": {}},
        "264": {"inputs": {"filename_prefix": "gate/video"}},
        "400": {"inputs": {"filename_prefix": "gate/latent"}},
        "405": {"inputs": {"source": ["400", 0]}},
        "401": {"inputs": {"latent_path": "h3_context/parent.safetensors"}},
    }


def _ws_trace(graph_sha, start, handshake_at):
    messages = [{"type": "status", "data": {"sid": CLIENT}},
                {"type": "progress_state", "data": {"prompt_id": PROMPT,
                 "nodes": {"226": {"prompt_id": PROMPT, "node_id": "226",
                                    "state": "running", "value": 0, "max": 1}}}}]
    messages += [{"type": "progress_state", "data": {"prompt_id": PROMPT,
                  "nodes": {"226": {"prompt_id": PROMPT, "node_id": "226",
                                     "state": "running", "value": step, "max": 12}}}}
                 for step in range(1, 13)]
    messages += [{"type": "progress_state", "data": {"prompt_id": PROMPT,
                  "nodes": {"226": {"prompt_id": PROMPT, "node_id": "226",
                                     "state": "finished", "value": 12, "max": 12}}}},
                 {"type": "executing", "data": {"prompt_id": PROMPT, "node": None}}]
    return {"run_id": RUN, "graph_sha256": graph_sha, "client_id": CLIENT,
            "closed_reason": "terminal", "events": [
                {"message": message,
                 "received_at_utc": (handshake_at if index == 0 else
                                     start + timedelta(seconds=index - 1)).isoformat(),
                 "received_monotonic_ns": (0 if index == 0 else
                                            int((start - handshake_at).total_seconds() * 1e9)
                                            + (index - 1) * 1_000_000_000)}
                for index, message in enumerate(messages)]}


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    start = now + timedelta(seconds=1)
    finish = start + timedelta(seconds=20)
    comfy_root = tmp_path / "ComfyUI"
    (comfy_root / "input").mkdir(parents=True)
    output_root = comfy_root / "output"
    staged_parent = "h3_gate1/run-fixture/parent-" + hashlib.sha256(b"parent").hexdigest()[:16] + ".safetensors"
    parent = output_root / staged_parent
    parent.parent.mkdir(parents=True)
    parent.write_bytes(b"parent")
    reference_graph = _graph()
    graph = copy.deepcopy(reference_graph)
    graph["401"]["inputs"]["latent_path"] = staged_parent
    reference = _write(tmp_path / "reference.json", reference_graph)
    candidate = _write(tmp_path / "candidate.json", graph)
    runner_root = tmp_path / "runner"
    model = comfy_root / "models/model.bin"
    source = runner_root / "src/adapter.py"
    model.parent.mkdir(parents=True)
    source.parent.mkdir(parents=True)
    model.write_bytes(b"model")
    source.write_bytes(b"source")
    sage_binary = tmp_path / "runtime" / "sageattention_sm120.so"
    sage_binary.parent.mkdir()
    sage_binary.write_bytes(b"sage-binary-fixture")
    manifest = {"reference_graph_sha256": _sha(reference),
                "parent": {"graph_path": "h3_context/parent.safetensors",
                           "sha256": _sha(parent), "bytes": parent.stat().st_size},
                "assets": [
                    {"kind": "model", "path": "ComfyUI/models/model.bin",
                     "sha256": _sha(model), "bytes": model.stat().st_size},
                    {"kind": "source", "path": "runner/src/adapter.py",
                     "sha256": _sha(source), "bytes": source.stat().st_size}]}
    manifest_path = _write(tmp_path / "manifest.json", manifest)
    addendum = _write(tmp_path / "audio-addendum.json", {
        "schema_version": 1, "base_manifest_sha256": _sha(manifest_path),
        "c1_validation_sha256": gate.C1_VALIDATION_SHA256,
        "c1_video_sha256": gate.C1_VIDEO_SHA256, "c1_video_bytes": 9947111,
        "primary_evidence_sha256": gate.C1_AUDIO_EVIDENCE_SHA256,
        "audio_contract": {"codec": "aac", "sample_rate": 32000, "channels": 2},
        "scope": "technical_media_format_only_not_visual_or_audio_quality_acceptance",
        "review_id": "astra-a3-c1-audio-20260926"})
    monkeypatch.setattr(gate, "APPROVED_AUDIO_ADDENDUM_SHA256", _sha(addendum))
    (output_root / "gate").mkdir(parents=True)
    video_baseline = _write(tmp_path / "video-baseline.json",
                            prefix_baseline(output_root, "gate/video", RUN))
    latent_baseline = _write(tmp_path / "latent-baseline.json",
                             prefix_baseline(output_root, "gate/latent", RUN))
    video = output_root / "gate/video_00001-audio.mp4"
    latent = output_root / "gate/latent_00001.safetensors"
    video.write_bytes(b"video-fixture")
    latent.write_bytes(b"latent-fixture")
    history = {PROMPT: {"prompt": [0, PROMPT, graph, {"client_id": CLIENT}],
                        "status": {"status_str": "success", "completed": True,
                                   "messages": [
                                       ["execution_start", {"prompt_id": PROMPT,
                                                            "timestamp": int(start.timestamp() * 1000)}],
                                       ["execution_cached", {"prompt_id": PROMPT,
                                                             "nodes": []}],
                                       ["execution_success", {"prompt_id": PROMPT,
                                                              "timestamp": int(finish.timestamp() * 1000)}]]},
                        "outputs": {"264": {"gifs": [
                            {"fullpath": str(video), "filename": video.name,
                             "type": "output", "format": "video/h264-mp4"}]},
                            "405": {"text": [str(latent)]}}}}
    history_path = _write(tmp_path / "history.json", history)
    ready_at = now - timedelta(seconds=2)
    run_dir = tmp_path / RUN
    ready = _write(run_dir / "ready.json", {
        "run_id": RUN, "graph_sha256": _sha(candidate), "client_id": CLIENT,
        "endpoint": "http://fixture.invalid", "observer_state": "connected",
        "observer_pid": 1234,
        "ready_at_utc": ready_at.isoformat()})
    claimed_at = datetime.now(timezone.utc)
    attempt = _write(run_dir / "attempt.json", {
        "run_id": RUN, "graph_sha256": _sha(candidate), "client_id": CLIENT,
        "endpoint": "http://fixture.invalid", "attempt_id": ATTEMPT,
        "state": "transport_may_have_started",
        "claimed_at_utc": claimed_at.isoformat()})
    prompt_file = _write(run_dir / "prompt.json", {
        "run_id": RUN, "client_id": CLIENT, "prompt_id": PROMPT,
        "graph_sha256": _sha(candidate), "endpoint": "http://fixture.invalid",
        "attempt_id": ATTEMPT,
        "published_at_utc": (claimed_at + timedelta(milliseconds=1)).isoformat()})
    environment = _write(tmp_path / "environment.json", {
        "run_id": RUN, "graph_sha256": _sha(candidate), "client_id": CLIENT,
        "endpoint": "http://fixture.invalid", "gpu_uuid": "GPU-fixture",
        "device_index": 0, "process_pid": 1234,
        "gpu_name": "NVIDIA GeForce RTX 5090", "compute_capability": "12.0",
        "profile": "rtx5090", "sage_binary_path": str(sage_binary),
        "sage_binary_sha256": _sha(sage_binary),
        "queue_state": {"prompt_id": PROMPT, "active_prompt_count": 1,
                        "sampler_cached": False},
        "process_started_at_utc": (now - timedelta(hours=1)).isoformat(),
        "source_hashes": {"runner/src/adapter.py": _sha(source)},
        "comfy_root": str(comfy_root.resolve()),
        "input_root": str((comfy_root / "input").resolve()),
        "runner_root": str(runner_root.resolve()),
        "driver": "fixture", "comfyui": "fixture", "torch": "fixture",
        "python": "fixture",
        "cuda": "fixture", "startup_flags": "fixture"})
    telemetry = tmp_path / "telemetry.jsonl"
    telemetry.write_text("\n".join(json.dumps({
        "at_utc": (start + timedelta(seconds=seconds)).isoformat(),
        "run_id": RUN, "process_pid": 1234, "gpu_uuid": "GPU-fixture",
        "device_index": 0, "utilization_pct": 90, "vram_mib": 30000})
        for seconds in (0, 5, 10, 15, 20)))
    trace = _write(tmp_path / "trace.json", _ws_trace(_sha(candidate), start, ready_at))
    monkeypatch.setattr(gate, "inspect_video", lambda path, contract: {
        "sha256": _sha(path), "audio_contract": {"tier": "derived_verified"}})
    monkeypatch.setattr(gate, "inspect_latent", lambda path: {"sha256": _sha(path), "finite": True})
    return gate.EvidenceFiles(RUN, PROMPT, "rtx5090", manifest_path,
                              reference, candidate, history_path, parent,
                              expected_manifest_sha256=_sha(manifest_path),
                              output_root=output_root, comfy_root=comfy_root,
                              runner_root=runner_root, ready=ready, attempt=attempt,
                              prompt_file=prompt_file, trace=trace,
                              video_baseline=video_baseline,
                              latent_baseline=latent_baseline, telemetry=telemetry,
                              environment=environment,
                              audio_addendum=addendum)


def test_complete_raw_bundle_reaches_only_deployment_screen(bundle):
    result = gate.evaluate_files(bundle)
    assert result["status"] == "deployment_combination_screen"
    assert result["checks"]["ws"]["observed_node_interval_s"] == 13
    assert result["environment_tier"] == "reported_only"
    assert result["checks"]["environment"]["tier"] == "reported_only"
    assert result["checks"]["candidate_profile"]["tier"] == "reported_only"
    assert result["checks"]["telemetry"]["sensor_tier"] == "reported_only"
    assert result["evidence_sha256"]["history"] == _sha(bundle.history)
    assert result["evidence_sha256"]["audio_addendum"] == _sha(bundle.audio_addendum)


def test_missing_ws_downgrades_after_other_evidence_passes(bundle):
    trace = json.loads(bundle.trace.read_text())
    trace["events"] = trace["events"][:1]
    trace["closed_reason"] = "disconnected"
    bundle.trace.write_text(json.dumps(trace))
    result = gate.evaluate_files(bundle)
    assert result["status"] == "server_wall_screen_sampler_unknown"
    assert result["checks"]["media"]["tier"] == "derived_verified"


def test_reported_5090_runtime_identity_is_required(bundle):
    assert gate.evaluate_files(replace(bundle, environment=None))["status"] == \
        "HISTORY_ONLY_NOT_SCREEN"


@pytest.mark.parametrize("change", [
    {"gpu_name": "NVIDIA A100-SXM4-80GB"},
    {"compute_capability": "8.0"},
    {"sage_binary_sha256": "0" * 64},
    {"sage_binary_path": "/missing/sage.so"},
    {"startup_flags": ["--input-directory=/other/input"]},
    {"startup_flags": "--output-directory=/other/output"},
    {"input_root": "/other/input"},
    {"queue_state": {"prompt_id": PROMPT, "active_prompt_count": 2,
                     "sampler_cached": False}},
])
def test_wrong_5090_runtime_identity_is_incomparable(bundle, change):
    environment = json.loads(bundle.environment.read_text())
    environment.update(change)
    bundle.environment.write_text(json.dumps(environment))
    result = gate.evaluate_files(bundle)
    assert result["status"] == "INCOMPARABLE"
    assert result["checks"]["environment"]["tier"] == "INCOMPARABLE"


def test_absent_observer_trace_is_not_a_screen(bundle):
    assert gate.evaluate_files(replace(bundle, trace=None))["status"] == \
        "HISTORY_ONLY_NOT_SCREEN"


def test_missing_media_or_audio_contract_is_not_a_screen(bundle):
    assert gate.evaluate_files(replace(bundle, video_baseline=None))["status"] == \
        "HISTORY_ONLY_NOT_SCREEN"
    assert gate.evaluate_files(replace(bundle, audio_addendum=None))["status"] == \
        "HISTORY_ONLY_NOT_SCREEN"
    assert gate.evaluate_files(replace(bundle, audio_addendum=bundle.audio_addendum.parent
                                       / "missing.json"))["status"] == \
        "HISTORY_ONLY_NOT_SCREEN"


def test_unapproved_audio_addendum_is_incomparable(bundle):
    addendum = json.loads(bundle.audio_addendum.read_text())
    addendum["audio_contract"]["channels"] = 1
    bundle.audio_addendum.write_text(json.dumps(addendum))
    result = gate.evaluate_files(bundle)
    assert result["status"] == "INCOMPARABLE"
    assert "not pre-approved" in result["checks"]["media"]["reason"]
    assert gate.evaluate_files(replace(bundle, video_baseline=None))["status"] == \
        "INCOMPARABLE"


def test_approved_addendum_rejects_another_manifest(bundle):
    manifest = json.loads(bundle.manifest.read_text())
    manifest["unrelated_revision"] = 1
    bundle.manifest.write_text(json.dumps(manifest))
    result = gate.evaluate_files(replace(bundle, expected_manifest_sha256=_sha(bundle.manifest)))
    assert result["status"] == "INCOMPARABLE"
    assert "does not bind" in result["checks"]["media"]["reason"]


def test_repository_audio_addendum_is_bound_to_frozen_manifest(bundle, monkeypatch):
    addendum = (Path(__file__).resolve().parents[1] / "docs/ops"
                / "2026-09-26-h3-c1-audio-addendum-candidate.json")
    monkeypatch.setattr(gate, "APPROVED_AUDIO_ADDENDUM_SHA256",
                        "949677963c5453c4924b9fbaef2cd49fa7063af631d2afe614c3e42ed6f89f52")
    hashes = {"manifest": gate.FROZEN_MANIFEST_SHA256}
    contract = gate._reviewed_audio_contract(replace(bundle, audio_addendum=addendum), hashes)
    assert (contract.sample_rate, contract.channels) == (32000, 2)
    assert hashes["audio_addendum"] == gate.APPROVED_AUDIO_ADDENDUM_SHA256


def test_baseline_captured_after_claim_is_incomparable(bundle):
    baseline = json.loads(bundle.video_baseline.read_text())
    claimed = datetime.fromisoformat(json.loads(bundle.attempt.read_text())["claimed_at_utc"])
    baseline["captured_at_utc"] = (claimed + timedelta(milliseconds=100)).isoformat()
    bundle.video_baseline.write_text(json.dumps(baseline))
    result = gate.evaluate_files(bundle)
    assert result["status"] == "INCOMPARABLE"
    assert "after submission claim" in result["checks"]["media"]["reason"]


@pytest.mark.parametrize("file_name,change", [
    ("ready", {"endpoint": None}),
    ("attempt", {"attempt_id": None}),
    ("attempt", {"endpoint": "http://foreign.invalid"}),
    ("prompt_file", {"graph_sha256": "0" * 64}),
])
def test_handoff_missing_or_foreign_identity_is_incomparable(bundle, file_name, change):
    path = getattr(bundle, file_name)
    record = json.loads(path.read_text())
    record.update(change)
    path.write_text(json.dumps(record))
    result = gate.evaluate_files(bundle)
    assert result["status"] == "INCOMPARABLE"
    assert result["checks"]["handoff"]["tier"] == "INCOMPARABLE"


def test_stale_ready_claim_is_incomparable(bundle):
    ready = json.loads(bundle.ready.read_text())
    claim = json.loads(bundle.attempt.read_text())
    ready["ready_at_utc"] = (datetime.fromisoformat(claim["claimed_at_utc"])
                             - timedelta(seconds=31)).isoformat()
    bundle.ready.write_text(json.dumps(ready))
    assert gate.evaluate_files(bundle)["checks"]["handoff"]["tier"] == "INCOMPARABLE"


def test_handoff_file_outside_run_namespace_is_incomparable(bundle, tmp_path):
    alternate = tmp_path / "other-attempt.json"
    alternate.write_bytes(bundle.attempt.read_bytes())
    result = gate.evaluate_files(replace(bundle, attempt=alternate))
    assert result["status"] == "INCOMPARABLE"
    assert "canonical run namespace" in result["checks"]["handoff"]["reason"]


def test_conflicting_prompt_or_gpu_identity_is_incomparable(bundle):
    prompt = json.loads(bundle.prompt_file.read_text())
    prompt["prompt_id"] = "foreign"
    bundle.prompt_file.write_text(json.dumps(prompt))
    assert gate.evaluate_files(replace(bundle, video_baseline=None))["status"] == "INCOMPARABLE"


def test_telemetry_gpu_mapping_mismatch_is_incomparable(bundle):
    environment = json.loads(bundle.environment.read_text())
    environment["gpu_uuid"] = "GPU-foreign"
    bundle.environment.write_text(json.dumps(environment))
    assert gate.evaluate_files(bundle)["status"] == "INCOMPARABLE"


def test_telemetry_hash_must_match_validated_bytes(bundle, monkeypatch):
    original = gate.verify_telemetry

    def mismatched_hash(*args, **kwargs):
        result = original(*args, **kwargs)
        result["raw_sha256"]["value"] = "0" * 64
        return result

    monkeypatch.setattr(gate, "verify_telemetry", mismatched_hash)
    result = gate.evaluate_files(bundle)
    assert result["status"] == "INCOMPARABLE"
    assert "changed during validation" in result["checks"]["telemetry"]["reason"]


def test_malformed_ws_downgrades_but_wrong_ws_identity_conflicts(bundle):
    bundle.trace.write_text("not json")
    assert gate.evaluate_files(bundle)["status"] == "HISTORY_ONLY_NOT_SCREEN"
    trace = _ws_trace(_sha(bundle.submitted_graph), datetime.now(timezone.utc),
                      datetime.fromisoformat(json.loads(bundle.ready.read_text())["ready_at_utc"]))
    trace["client_id"] = "foreign"
    bundle.trace.write_text(json.dumps(trace))
    assert gate.evaluate_files(bundle)["status"] == "INCOMPARABLE"


def test_ready_and_ws_handshake_contradiction_is_incomparable(bundle):
    trace = json.loads(bundle.trace.read_text())
    trace["events"][0]["message"]["data"]["sid"] = "foreign"
    bundle.trace.write_text(json.dumps(trace))
    result = gate.evaluate_files(bundle)
    assert result["status"] == "INCOMPARABLE"
    assert result["checks"]["observer_handshake"]["tier"] == "INCOMPARABLE"


def test_prompt_bound_ws_outside_history_interval_is_incomparable(bundle):
    trace = json.loads(bundle.trace.read_text())
    for event in trace["events"][1:]:
        timestamp = datetime.fromisoformat(event["received_at_utc"])
        event["received_at_utc"] = (timestamp + timedelta(minutes=10)).isoformat()
    bundle.trace.write_text(json.dumps(trace))
    result = gate.evaluate_files(bundle)
    assert result["status"] == "INCOMPARABLE"
    assert "outside history" in result["checks"]["ws"]["reason"]
