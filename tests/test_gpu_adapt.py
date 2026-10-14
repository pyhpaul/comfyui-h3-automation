from __future__ import annotations

import json
from pathlib import Path

import pytest

from comfy_orch.gpu_adapt import (
    NODE_LORA,
    NODE_SAGE,
    NODE_UNET,
    GpuProfile,
    apply_gpu_profile,
    detect_gpu_profile_id,
    resolve_gpu_profile,
)

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "templates" / "yz_h3_ep_unit" / "workflow_api.json"


def test_detect_primary_5090():
    assert detect_gpu_profile_id("cuda:0 NVIDIA GeForce RTX 5090") == "rtx5090"


def test_detect_backup_4080():
    assert detect_gpu_profile_id("cuda:0 NVIDIA GeForce RTX 4080 SUPER : cudaMallocAsync") == "rtx4080"


def test_detect_unknown_defaults_to_backup():
    assert detect_gpu_profile_id("cuda:0 Some Other GPU") == "rtx4080"


def test_resolve_auto_uses_device_name():
    p = resolve_gpu_profile("auto", device_name="NVIDIA GeForce RTX 5090")
    assert p.id == "rtx5090"
    assert p.attention == "minimax_sage_fp8"


def test_rtx5090_keeps_minimax_sage_patch():
    raw = json.loads(API.read_text(encoding="utf-8"))
    out = apply_gpu_profile(raw, GpuProfile.by_id("rtx5090"))
    assert out[NODE_SAGE]["class_type"] == "MiniMaxH3MemoryEfficientSageAttentionPatch"
    assert out[NODE_LORA]["inputs"]["model"] == [NODE_SAGE, 0]


def test_rtx4080_bypasses_sage_patch():
    raw = json.loads(API.read_text(encoding="utf-8"))
    out = apply_gpu_profile(raw, GpuProfile.by_id("rtx4080"))
    assert NODE_SAGE not in out
    assert out[NODE_LORA]["inputs"]["model"] == [NODE_UNET, 0]


def test_a100_sage_is_opt_in_only():
    auto = resolve_gpu_profile("auto", device_name="NVIDIA A100-SXM4-80GB")
    experimental = resolve_gpu_profile("a100_sage_sm80", device_name="NVIDIA A100-SXM4-80GB")
    assert auto.attention == "bypass"
    assert experimental.attention == "minimax_sage_sm80"

    raw = json.loads(API.read_text(encoding="utf-8"))
    out = apply_gpu_profile(raw, experimental)
    assert out[NODE_SAGE]["class_type"] == "MiniMaxH3MemoryEfficientSageAttentionPatch"
    assert out[NODE_LORA]["inputs"]["model"] == [NODE_SAGE, 0]


def test_a100_sage_rejects_non_a100_device():
    with pytest.raises(ValueError, match="requires a detected A100"):
        resolve_gpu_profile("a100_sage_sm80", device_name="NVIDIA GeForce RTX 5090")


def test_a100_candidate_changes_only_attention_node_and_lora_edge():
    raw = json.loads(API.read_text(encoding="utf-8"))
    baseline = apply_gpu_profile(raw, GpuProfile.by_id("rtx4080"))
    candidate = apply_gpu_profile(raw, GpuProfile.by_id("a100_sage_sm80"))
    candidate_lora = json.loads(json.dumps(candidate[NODE_LORA]))
    candidate_lora["inputs"]["model"] = [NODE_UNET, 0]
    candidate_without_patch = {key: value for key, value in candidate.items() if key != NODE_SAGE}
    candidate_without_patch[NODE_LORA] = candidate_lora
    assert candidate_without_patch == baseline


def test_rtx4080_can_override_to_flash():
    raw = json.loads(API.read_text(encoding="utf-8"))
    out = apply_gpu_profile(
        raw,
        GpuProfile(id="rtx4080", label="flash", attention="flash"),
    )
    assert out[NODE_SAGE]["class_type"] == "PatchFlashAttentionKJ"


def test_bypass_rewires_lora_to_unet():
    raw = json.loads(API.read_text(encoding="utf-8"))
    out = apply_gpu_profile(
        raw,
        GpuProfile(id="rtx4080", label="bypass-test", attention="bypass"),
    )
    assert NODE_SAGE not in out
    assert out[NODE_LORA]["inputs"]["model"] == [NODE_UNET, 0]
