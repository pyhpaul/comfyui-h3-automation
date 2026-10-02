"""Offline fixtures for the strict cross-GPU comparison gate."""

import copy
import hashlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
from h3_cross_gpu_gate0 import (Incomparable, compare_graphs, validate_history,
                                validate_receipt, validate_sampler_log)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _graph() -> dict:
    return {
        "58": {"class_type": "MiniMaxH3MemoryEfficientSageAttentionPatch",
               "inputs": {"model": ["192", 0]}},
        "128": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["58", 0]}},
        "192": {"class_type": "UNETLoader", "inputs": {"unet_name": "model.safetensors"}},
        "256": {"class_type": "RandomNoise", "inputs": {"noise_seed": 123}},
        "255": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "261": {"class_type": "BasicScheduler", "inputs": {"steps": 16}},
        "289": {"class_type": "SplitSigmas", "inputs": {"step": 12}},
        "264": {"class_type": "VHS_VideoCombine", "inputs": {"filename_prefix": "control"}},
        "400": {"class_type": "MiniMaxH3MotionContextSaveLatent",
                "inputs": {"filename_prefix": "control-latent"}},
        "401": {"class_type": "MiniMaxH3MotionContextLoadLatent",
                "inputs": {"latent_path": "h3_context/ep04_u01_00001.safetensors", "clip_index": 1}},
    }


@pytest.fixture
def frozen(tmp_path):
    parent = tmp_path / "parent.safetensors"
    parent.write_bytes(b"frozen A100 parent")
    manifest = {
        "parent": {"graph_path": "h3_context/ep04_u01_00001.safetensors",
                   "sha256": _sha(parent.read_bytes()), "bytes": parent.stat().st_size},
        "assets": [
            {"kind": "model", "path": "ComfyUI/models/model.safetensors",
             "bytes": 5, "sha256": _sha(b"model")},
            {"kind": "source", "path": "runner/src/adapter.py",
             "bytes": 6, "sha256": _sha(b"source")},
        ],
    }
    return manifest, _graph(), parent


def _receipt(manifest):
    start = datetime(2026, 9, 26, tzinfo=timezone.utc)
    prompt_id = "prompt-1"
    return {
        "schema_version": 1,
        "manifest_sha256": "a" * 64,
        "graph_sha256": "b" * 64,
        "profile": "rtx5090",
        "parent_graph_path": "h3_gate1/run-1/parent-" + manifest["parent"]["sha256"][:16] + ".safetensors",
        "parent_sha256": manifest["parent"]["sha256"],
        "assets": {item["path"]: {"bytes": item["bytes"], "sha256": item["sha256"]}
                   for item in manifest["assets"]},
        "environment": {
            "gpu": "RTX 5090", "driver": "fixture", "sm_clock": 2000,
            "python": "fixture", "torch": "fixture", "cuda": "fixture",
            "sage_binary_sha256": "c" * 64, "comfyui": "fixture",
            "startup_flags": "fixture", "process_started_at_utc": (start - timedelta(minutes=5)).isoformat(),
            "process_pid": 1234,
        },
        "execution": {
            "prompt_id": prompt_id, "started_at_utc": start.isoformat(),
            "finished_at_utc": (start + timedelta(seconds=65)).isoformat(),
            "history_status": "success", "cache_status": "executed",
            "interleaved_prompts": False, "sampler_node_id": "226",
            "correlation_source": "fixture isolated trace",
            "server_timing_source": "fixture server log",
            "sampler_timing_source": "fixture sampler log",
            "server_wall_s": 65, "sampler_wall_s": 60,
            "sampler_log_sha256": "3" * 64,
            "log_capture": {
                "method": "append_only_byte_range", "process_pid": 1234,
                "byte_start": 100, "byte_end": 500,
                "started_at_utc": (start - timedelta(seconds=1)).isoformat(),
                "finished_at_utc": (start + timedelta(seconds=66)).isoformat(),
            },
            "steps": [
                {"prompt_id": prompt_id, "sampler_node_id": "226", "step": number,
                 "at_utc": (start + timedelta(seconds=5 * number)).isoformat(),
                 "elapsed_s": 5 * number}
                for number in range(1, 13)
            ],
        },
        "gpu_telemetry": [
            {"at_utc": (start + timedelta(seconds=5 * number)).isoformat(),
             "utilization_pct": 95, "vram_mib": 30000}
            for number in range(14)
        ],
        "operations_wall_s": {"setup": 0, "restore": 0, "transfer": 1, "backup": 1},
        "media": {
            "latent_finite": True, "video_frames": 306, "audio_frames": 400,
            "video_duration_s": 12.75, "audio_duration_s": 12.75,
            "decoded_video_sha256": "d" * 64,
            "decoded_audio_sha256": "e" * 64,
            "latent_sha256": "f" * 64,
            "video_timeline_sha256": "1" * 64,
            "audio_timeline_sha256": "2" * 64,
            "video_time_base": "1/12288", "audio_time_base": "1/32000",
        },
    }


def _validate(manifest, receipt):
    validate_receipt(manifest, "a" * 64, "b" * 64, receipt,
                     "rtx5090", receipt["parent_graph_path"])


def test_archived_style_a100_graphs_allow_only_prefixes(frozen):
    manifest, reference, parent = frozen
    candidate = copy.deepcopy(reference)
    candidate["264"]["inputs"]["filename_prefix"] = "C2"
    candidate["400"]["inputs"]["filename_prefix"] = "C2-latent"
    compare_graphs(manifest, reference, candidate, "a100_sage_sm80", parent)


def test_5090_requires_unique_hash_bound_parent_staging(frozen, tmp_path):
    manifest, reference, parent = frozen
    staging = "h3_gate1/run-1/parent-" + manifest["parent"]["sha256"][:16] + ".safetensors"
    staged_file = tmp_path / staging
    staged_file.parent.mkdir(parents=True)
    staged_file.write_bytes(parent.read_bytes())
    candidate = copy.deepcopy(reference)
    candidate["401"]["inputs"]["latent_path"] = staging
    compare_graphs(manifest, reference, candidate, "rtx5090", staged_file, tmp_path,
                   expected_run_id="run-1")
    with pytest.raises(Incomparable, match="staged file"):
        compare_graphs(manifest, reference, candidate, "rtx5090", parent, tmp_path,
                       expected_run_id="run-1")


def test_5090_reference_aliases_require_same_run_and_frozen_bytes(frozen, tmp_path):
    manifest, reference, parent = frozen
    reference["50"] = {"class_type": "LoadImage", "inputs": {"image": "id0.png"}}
    reference["51"] = {"class_type": "LoadImage", "inputs": {"image": "id2.png"}}
    manifest["assets"].extend([
        {"kind": "reference", "path": "runner/assets/id0.png",
         "bytes": 3, "sha256": _sha(b"id0")},
        {"kind": "reference", "path": "runner/assets/id2.png",
         "bytes": 3, "sha256": _sha(b"id2")},
    ])
    staging = "h3_gate1/run-1/parent-" + manifest["parent"]["sha256"][:16] + ".safetensors"
    output_root = tmp_path / "output"
    staged_parent = output_root / staging
    staged_parent.parent.mkdir(parents=True)
    staged_parent.write_bytes(parent.read_bytes())
    input_root = tmp_path / "input"
    refs = input_root / "h3_gate1/run-1/refs"
    refs.mkdir(parents=True)
    (refs / "id0.png").write_bytes(b"id0")
    (refs / "id2.png").write_bytes(b"id2")
    (input_root / "id0.png").write_bytes(b"old")
    candidate = copy.deepcopy(reference)
    candidate["401"]["inputs"]["latent_path"] = staging
    candidate["50"]["inputs"]["image"] = "h3_gate1/run-1/refs/id0.png"
    candidate["51"]["inputs"]["image"] = "h3_gate1/run-1/refs/id2.png"
    compare_graphs(manifest, reference, candidate, "rtx5090", staged_parent,
                   output_root, input_root, "run-1")

    changed = copy.deepcopy(candidate)
    changed["50"]["inputs"]["image"] = "id0.png"
    with pytest.raises(Incomparable, match="reference image bytes differ"):
        compare_graphs(manifest, reference, changed, "rtx5090", staged_parent,
                       output_root, input_root, "run-1")
    changed["50"]["inputs"]["image"] = "h3_gate1/other-run/refs/id0.png"
    with pytest.raises(Incomparable, match="reference image path differs"):
        compare_graphs(manifest, reference, changed, "rtx5090", staged_parent,
                       output_root, input_root, "run-1")
    (refs / "id0.png").write_bytes(b"bad")
    with pytest.raises(Incomparable, match="reference image bytes differ"):
        compare_graphs(manifest, reference, candidate, "rtx5090", staged_parent,
                       output_root, input_root, "run-1")
    (refs / "id0.png").write_bytes(b"id0")
    with pytest.raises(Incomparable, match="hash-bound staging path"):
        compare_graphs(manifest, reference, candidate, "rtx5090", staged_parent,
                       output_root, input_root, "other-run")
    stage_root = input_root / "h3_gate1"
    stage_root.rename(input_root / "real-h3_gate1")
    stage_root.symlink_to("real-h3_gate1", target_is_directory=True)
    with pytest.raises(Incomparable, match="contains a symlink"):
        compare_graphs(manifest, reference, candidate, "rtx5090", staged_parent,
                       output_root, input_root, "run-1")


def test_5090_rejects_bypass_even_when_generic_normalizer_accepts_it(frozen, tmp_path):
    manifest, reference, parent = frozen
    candidate = copy.deepcopy(reference)
    candidate.pop("58")
    candidate["128"]["inputs"]["model"] = ["192", 0]
    with pytest.raises(Incomparable, match="bypass"):
        compare_graphs(manifest, reference, candidate, "rtx5090", parent, tmp_path,
                       expected_run_id="run-1")


@pytest.mark.parametrize("node,field,value", [
    ("256", "noise_seed", 124),
    ("255", "sampler_name", "dpmpp_2m"),
    ("289", "step", 11),
    ("401", "clip_index", 2),
])
def test_graph_setting_change_is_incomparable(frozen, node, field, value):
    manifest, reference, parent = frozen
    candidate = copy.deepcopy(reference)
    candidate[node]["inputs"][field] = value
    with pytest.raises(Incomparable, match="submitted graph differs"):
        compare_graphs(manifest, reference, candidate, "a100_sage_sm80", parent)


def test_parent_byte_change_is_incomparable(frozen):
    manifest, reference, parent = frozen
    parent.write_bytes(b"different parent")
    with pytest.raises(Incomparable, match="parent bytes"):
        compare_graphs(manifest, reference, reference, "a100_sage_sm80", parent)


def test_complete_prompt_bound_receipt_is_valid(frozen):
    manifest, _, _ = frozen
    _validate(manifest, _receipt(manifest))


def test_isolated_progress_does_not_require_invented_step_utc(frozen):
    manifest, _, _ = frozen
    receipt = _receipt(manifest)
    for step in receipt["execution"]["steps"]:
        step.pop("at_utc")
    _validate(manifest, receipt)


def test_source_delta_requires_file_specific_reviewed_hash(frozen):
    manifest, _, _ = frozen
    receipt = _receipt(manifest)
    source = receipt["assets"]["runner/src/adapter.py"]
    source.update(bytes=7, sha256=_sha(b"changed"))
    with pytest.raises(Incomparable, match="source delta"):
        _validate(manifest, receipt)
    source["source_delta_reason"] = "architecture-specific adapter; graph unchanged"
    with pytest.raises(Incomparable, match="source delta"):
        _validate(manifest, receipt)
    manifest["approved_source_deltas"] = {
        "runner/src/adapter.py": [{"bytes": 7, "sha256": _sha(b"changed"),
                                   "review_id": "reviewed-diff-fixture"}]}
    _validate(manifest, receipt)


@pytest.mark.parametrize("change,reason", [
    (lambda r: r["execution"]["steps"][4].update(prompt_id="another-prompt"), "mixed"),
    (lambda r: r["execution"]["steps"].pop(), "exactly 12"),
    (lambda r: r["execution"]["steps"][4].update(step=4), "out of order"),
    (lambda r: r["execution"].update(cache_status="cached"), "cache"),
    (lambda r: r["execution"].update(interleaved_prompts=True), "cache"),
    (lambda r: r.update(manifest_sha256="0" * 64), "manifest"),
    (lambda r: r["environment"].update(sage_binary_sha256="unknown"), "sage_binary"),
    (lambda r: r["media"].update(video_timeline_sha256=""), "media digest"),
])
def test_receipt_rejects_incomplete_or_stitched_evidence(frozen, change, reason):
    manifest, _, _ = frozen
    receipt = _receipt(manifest)
    change(receipt)
    with pytest.raises(Incomparable, match=reason):
        _validate(manifest, receipt)


def test_step_outside_target_prompt_interval_is_rejected(frozen):
    manifest, _, _ = frozen
    receipt = _receipt(manifest)
    receipt["execution"]["steps"][0]["at_utc"] = "2026-09-25T23:59:59+00:00"
    with pytest.raises(Incomparable, match="target prompt interval"):
        _validate(manifest, receipt)


def test_history_binds_prompt_graph_and_server_timing(frozen):
    manifest, candidate, _ = frozen
    receipt = _receipt(manifest)
    execution = receipt["execution"]
    prompt_id = execution["prompt_id"]
    start_ms = int(datetime.fromisoformat(execution["started_at_utc"]).timestamp() * 1000)
    history = {prompt_id: {
        "prompt": [0, prompt_id, candidate, {}, []],
        "status": {"status_str": "success", "completed": True, "messages": [
            ["execution_start", {"prompt_id": prompt_id, "timestamp": start_ms}],
            ["execution_cached", {"prompt_id": prompt_id, "nodes": [], "timestamp": start_ms}],
            ["execution_success", {"prompt_id": prompt_id, "timestamp": start_ms + 65000}],
        ]},
    }}
    validate_history(receipt, history, candidate)
    history[prompt_id]["status"]["messages"][1][1]["nodes"] = ["226"]
    with pytest.raises(Incomparable, match="cached"):
        validate_history(receipt, history, candidate)


def test_sampler_log_rejects_stitched_prompts(frozen, tmp_path):
    manifest, _, _ = frozen
    receipt = _receipt(manifest)
    progress = "got prompt\n" + "\n".join(
        f"{number}/12 [{5 * number // 60:02d}:{5 * number % 60:02d}<00:01]"
        for number in range(1, 13)) + "\nPrompt executed in 65 seconds\n"
    log_file = tmp_path / "isolated.log"
    log_file.write_text(progress)
    receipt["execution"]["sampler_log_sha256"] = _sha(log_file.read_bytes())
    validate_sampler_log(receipt, log_file)
    log_file.write_text(progress + progress)
    receipt["execution"]["sampler_log_sha256"] = _sha(log_file.read_bytes())
    with pytest.raises(Incomparable, match="single-prompt"):
        validate_sampler_log(receipt, log_file)
