"""GPU / attention adaptations for YZ H3 workflows.

Two stock profiles:

- ``rtx5090`` (primary): keep template ``MiniMaxH3MemoryEfficientSageAttentionPatch``
  (FP8 sage path used on the 5090 node).
- ``rtx4080`` (backup): remove the MiniMax FP8 Sage patch and wire UNET→LoRA
  directly (``bypass``). Ada boxes often lack FA2/FA3 and FP8 sage kernels;
  override to ``sage_fp16`` / ``flash`` when those deps exist.

``auto`` resolves from Comfy ``/system_stats`` device name; unknown GPUs fall
back to the safer ``rtx4080`` profile.
"""
from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from typing import Any, Literal

GpuProfileId = Literal["rtx5090", "rtx4080"]
AttentionMode = Literal["minimax_sage_fp8", "sage_fp16", "flash", "bypass"]

NODE_SAGE = "58"
NODE_UNET = "192"
NODE_LORA = "128"


@dataclass(frozen=True)
class GpuProfile:
    id: GpuProfileId
    label: str
    attention: AttentionMode
    # Optional job-field override (None = leave job megapixels unchanged).
    megapixels: float | None = None

    @staticmethod
    def by_id(profile_id: GpuProfileId) -> "GpuProfile":
        try:
            return PROFILES[profile_id]
        except KeyError as exc:
            raise ValueError(f"unknown gpu profile: {profile_id!r}") from exc


PROFILES: dict[GpuProfileId, GpuProfile] = {
    "rtx5090": GpuProfile(
        id="rtx5090",
        label="primary RTX 5090",
        attention="minimax_sage_fp8",
    ),
    "rtx4080": GpuProfile(
        id="rtx4080",
        label="backup RTX 4080 SUPER",
        attention="bypass",
    ),
}


def detect_gpu_profile_id(device_name: str) -> GpuProfileId:
    text = (device_name or "").casefold()
    if "5090" in text:
        return "rtx5090"
    if "4080" in text or "4090" in text:
        return "rtx4080"
    # Prefer the portable attention path when the card is unknown.
    return "rtx4080"


def resolve_gpu_profile(
    requested: str | None = None,
    *,
    device_name: str | None = None,
) -> GpuProfile:
    """Resolve profile from CLI/env (``auto|rtx5090|rtx4080``) + optional doctor name."""
    raw = (requested if requested is not None else os.environ.get("COMFY_GPU_PROFILE", "auto")) or "auto"
    key = raw.strip().casefold()
    if key in {"auto", ""}:
        return GpuProfile.by_id(detect_gpu_profile_id(device_name or ""))
    if key in {"rtx5090", "5090", "primary"}:
        return GpuProfile.by_id("rtx5090")
    if key in {"rtx4080", "4080", "backup"}:
        return GpuProfile.by_id("rtx4080")
    raise ValueError(
        f"unknown gpu profile {raw!r}; expected auto|rtx5090|rtx4080"
    )


def apply_gpu_profile(
    workflow: dict[str, Any],
    profile: GpuProfile,
) -> dict[str, Any]:
    """Return a copy of ``workflow`` with attention nodes adapted for ``profile``."""
    out = copy.deepcopy(workflow)
    if profile.attention == "minimax_sage_fp8":
        out[NODE_SAGE] = {
            "class_type": "MiniMaxH3MemoryEfficientSageAttentionPatch",
            "inputs": {"model": [NODE_UNET, 0]},
            "_meta": {"title": "MiniMaxH3MemoryEfficientSageAttentionPatch"},
        }
        out[NODE_LORA]["inputs"]["model"] = [NODE_SAGE, 0]
        return out

    if profile.attention == "sage_fp16":
        out[NODE_SAGE] = {
            "class_type": "PathchSageAttentionKJ",
            "inputs": {
                "model": [NODE_UNET, 0],
                "sage_attention": "sageattn_qk_int8_pv_fp16_cuda",
                "allow_compile": False,
            },
            "_meta": {"title": "SageAttention FP16 (4080 backup)"},
        }
        out[NODE_LORA]["inputs"]["model"] = [NODE_SAGE, 0]
        return out

    if profile.attention == "flash":
        out[NODE_SAGE] = {
            "class_type": "PatchFlashAttentionKJ",
            "inputs": {
                "model": [NODE_UNET, 0],
                "allow_compile": False,
            },
            "_meta": {"title": "FlashAttention (4080 fallback)"},
        }
        out[NODE_LORA]["inputs"]["model"] = [NODE_SAGE, 0]
        return out

    if profile.attention == "bypass":
        out.pop(NODE_SAGE, None)
        out[NODE_LORA]["inputs"]["model"] = [NODE_UNET, 0]
        return out

    raise ValueError(f"unsupported attention mode: {profile.attention!r}")
