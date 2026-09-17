from __future__ import annotations

import json
from pathlib import Path

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
