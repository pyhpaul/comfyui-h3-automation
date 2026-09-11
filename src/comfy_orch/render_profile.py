"""Render profile overlays for YZ H3 API workflows.

Two orthogonal switches (default = original automation behavior):

- continuity: ``ref_video`` (MP4 → YZ参考视频 + optional ``<Video 1>``)
  vs ``motion_latent`` (Motion Context Save/Load on 一采 AV latent)
- second_pass: if True, attach LatentUpscaler3D + 二采采样 + combine 214

Profiles mutate a deep copy of ``workflow_api.json``; they do not replace the
stock template file, so both modes coexist.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Literal

ContinuityMode = Literal["ref_video", "motion_latent"]

NODE_PASS1_SAMPLER = "226"
NODE_PASS1_GUIDER = "223"
NODE_PASS1_COMBINE = "264"
NODE_PASS1_DECODE = "253"
NODE_PASS1_DECODE_AUDIO = "254"
NODE_H3 = "265"
NODE_SPLIT_SIGMAS = "289"
NODE_NOISE = "256"
NODE_SAMPLER_SELECT = "255"
NODE_VIDEO_VAE = "36"
NODE_AUDIO_VAE = "37"
NODE_UPSCALE_SCALE = "283"
NODE_MODEL = "53"

NODE_SAVE = "400"
NODE_LOAD = "401"
NODE_MOTION = "402"
NODE_TRIM = "403"
NODE_SEP = "139"
NODE_UPSCALE = "140"
NODE_CONCAT = "142"
NODE_PASS2_SAMPLER = "144"
NODE_PASS2_DECODE = "116"
NODE_PASS2_DECODE_AUDIO = "115"
NODE_PASS2_COMBINE = "214"
NODE_PASS2_GUIDER = "406"
NODE_SAVE_PREVIEW = "405"


@dataclass(frozen=True)
class RenderProfile:
    continuity: ContinuityMode = "ref_video"
    second_pass: bool = False
    context_length: str = "22"
    audio_context_length: int = 24
    save_clip_index: int = 1
    load_clip_index: int = 0
    motion_latent_path: str | None = None
    latent_filename_prefix: str = "h3_context/ep_unit"
    pass2_scale: float = 1.5


def apply_render_profile(
    workflow: dict[str, Any],
    profile: RenderProfile,
    *,
    filename_prefix: str | None = None,
) -> dict[str, Any]:
    """Return a copy of ``workflow`` with continuity / second-pass overlays."""
    out = copy.deepcopy(workflow)
    out.pop("328", None)

    if profile.continuity == "motion_latent":
        _apply_motion_latent(out, profile)
    if profile.second_pass:
        _apply_second_pass(out, profile, filename_prefix=filename_prefix)
    elif profile.continuity == "motion_latent" and NODE_MOTION in out:
        _attach_trim(
            out,
            images_from=(NODE_PASS1_DECODE, 0),
            audio_from=(NODE_PASS1_DECODE_AUDIO, 0),
            combine_id=NODE_PASS1_COMBINE,
        )

    if filename_prefix and NODE_PASS1_COMBINE in out:
        out[NODE_PASS1_COMBINE]["inputs"]["filename_prefix"] = f"{filename_prefix}-pass1"
        out[NODE_PASS1_COMBINE]["inputs"]["save_output"] = True
    if profile.second_pass and filename_prefix and NODE_PASS2_COMBINE in out:
        out[NODE_PASS2_COMBINE]["inputs"]["filename_prefix"] = f"{filename_prefix}-pass2"
        out[NODE_PASS2_COMBINE]["inputs"]["save_output"] = True
    return out


def _apply_motion_latent(workflow: dict[str, Any], profile: RenderProfile) -> None:
    workflow[NODE_SAVE] = {
        "class_type": "MiniMaxH3MotionContextSaveLatent",
        "inputs": {
            "latent": [NODE_PASS1_SAMPLER, 1],
            "filename_prefix": profile.latent_filename_prefix,
            "clip_index": int(profile.save_clip_index),
        },
        "_meta": {"title": "H3 Motion Context Save Latent"},
    }
    # STRING outputs are often missing from /history; PreviewAny keeps the
    # save node on the executed output set and surfaces the path in UI.
    workflow[NODE_SAVE_PREVIEW] = {
        "class_type": "PreviewAny",
        "inputs": {"source": [NODE_SAVE, 0]},
        "_meta": {"title": "Preview Motion Context Latent Path"},
    }

    h3 = workflow.get(NODE_H3)
    if isinstance(h3, dict):
        inputs = dict(h3.get("inputs") or {})
        for key in list(inputs):
            if key.startswith("ref_videos."):
                del inputs[key]
        h3["inputs"] = inputs
    workflow.pop("27", None)

    if not (profile.motion_latent_path and int(profile.load_clip_index) > 0):
        return

    workflow[NODE_LOAD] = {
        "class_type": "MiniMaxH3MotionContextLoadLatent",
        "inputs": {
            "latent_path": profile.motion_latent_path,
            "clip_index": int(profile.load_clip_index),
        },
        "_meta": {"title": "H3 Motion Context Load Latent"},
    }
    workflow[NODE_MOTION] = {
        "class_type": "MiniMaxH3MotionContext",
        "inputs": {
            "conditioning": [NODE_H3, 0],
            "vae": [NODE_VIDEO_VAE, 0],
            "latent": [NODE_H3, 1],
            "context_length": str(profile.context_length),
            "audio_context_length": int(profile.audio_context_length),
            "context_latent": [NODE_LOAD, 0],
            "audio_vae": [NODE_AUDIO_VAE, 0],
        },
        "_meta": {"title": "MiniMax H3 Motion Context"},
    }
    workflow[NODE_PASS1_GUIDER]["inputs"]["conditioning"] = [NODE_MOTION, 0]


def _attach_trim(
    workflow: dict[str, Any],
    *,
    images_from: tuple[str, int],
    audio_from: tuple[str, int],
    combine_id: str,
) -> None:
    workflow[NODE_TRIM] = {
        "class_type": "MiniMaxH3MotionContextTrim",
        "inputs": {
            "images": [images_from[0], images_from[1]],
            "trim_frames": [NODE_MOTION, 1],
            "audio": [audio_from[0], audio_from[1]],
            "fps": 24.0,
            "match_tail": True,
        },
        "_meta": {"title": "H3 Motion Context Trim"},
    }
    workflow[combine_id]["inputs"]["images"] = [NODE_TRIM, 0]
    workflow[combine_id]["inputs"]["audio"] = [NODE_TRIM, 1]


def _apply_second_pass(
    workflow: dict[str, Any],
    profile: RenderProfile,
    *,
    filename_prefix: str | None,
) -> None:
    workflow[NODE_UPSCALE_SCALE] = {
        "class_type": "easy float",
        "inputs": {"value": float(profile.pass2_scale)},
        "_meta": {"title": "二采倍数"},
    }
    workflow[NODE_SEP] = {
        "class_type": "LTXVSeparateAVLatent",
        "inputs": {"av_latent": [NODE_PASS1_SAMPLER, 1]},
        "_meta": {"title": "分离 AV Latent"},
    }
    workflow[NODE_UPSCALE] = {
        "class_type": "MinimaxH3LatentUpscaler3D",
        "inputs": {
            "latent": [NODE_SEP, 0],
            "model_name": "minimax_h3_latent_upscaler_3d_fp16.safetensors",
            "mode": "scale by multiplier",
            "mode.scale": [NODE_UPSCALE_SCALE, 0],
            "align": 32,
            "enable_temporal_chunking": True,
            "force_unload": True,
            "device": "cuda",
            "precision": "fp16",
        },
        "_meta": {"title": "H3 Latent Upscaler 3D"},
    }
    workflow[NODE_CONCAT] = {
        "class_type": "LTXVConcatAVLatent",
        "inputs": {
            "video_latent": [NODE_UPSCALE, 0],
            "audio_latent": [NODE_SEP, 1],
        },
        "_meta": {"title": "合并 AV Latent"},
    }
    # Pass2 must NOT reuse a MotionContext guider: pinned context rows are
    # sized for the 一采 latent. After spatial upscale the shapes diverge and
    # SamplerCustomAdvanced fails with broadcast errors. The 一采 latent already
    # baked continuity; pass2 only refines detail with the base H3 conditioning.
    workflow[NODE_PASS2_GUIDER] = {
        "class_type": "BasicGuider",
        "inputs": {
            "model": [NODE_MODEL, 0],
            "conditioning": [NODE_H3, 0],
        },
        "_meta": {"title": "二采引导器"},
    }
    workflow[NODE_PASS2_SAMPLER] = {
        "class_type": "SamplerCustomAdvanced",
        "inputs": {
            "noise": [NODE_NOISE, 0],
            "guider": [NODE_PASS2_GUIDER, 0],
            "sampler": [NODE_SAMPLER_SELECT, 0],
            "sigmas": [NODE_SPLIT_SIGMAS, 1],
            "latent_image": [NODE_CONCAT, 0],
        },
        "_meta": {"title": "二采采样"},
    }
    workflow[NODE_PASS2_DECODE] = {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": [NODE_PASS2_SAMPLER, 1],
            "vae": [NODE_VIDEO_VAE, 0],
        },
        "_meta": {"title": "二采 VAE 解码"},
    }
    workflow[NODE_PASS2_DECODE_AUDIO] = {
        "class_type": "VAEDecodeAudio",
        "inputs": {
            "samples": [NODE_PASS2_SAMPLER, 1],
            "vae": [NODE_AUDIO_VAE, 0],
        },
        "_meta": {"title": "二采音频解码"},
    }

    prefix = f"{filename_prefix}-pass2" if filename_prefix else "YZ_H3_二采"
    workflow[NODE_PASS2_COMBINE] = {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "frame_rate": 24,
            "loop_count": 0,
            "filename_prefix": prefix,
            "format": "video/h264-mp4",
            "pix_fmt": "yuv420p",
            "crf": 19,
            "save_metadata": True,
            "trim_to_audio": False,
            "pingpong": False,
            "save_output": True,
            "images": [NODE_PASS2_DECODE, 0],
            "audio": [NODE_PASS2_DECODE_AUDIO, 0],
        },
        "_meta": {"title": "YZ二采成片输出"},
    }

    if profile.continuity == "motion_latent" and NODE_MOTION in workflow:
        _attach_trim(
            workflow,
            images_from=(NODE_PASS2_DECODE, 0),
            audio_from=(NODE_PASS2_DECODE_AUDIO, 0),
            combine_id=NODE_PASS2_COMBINE,
        )


def motion_context_slot_relpath(filename_prefix: str, clip_index: int) -> str:
    """Relative path under Comfy output for an indexed Motion Context save.

    Mirrors MiniMaxH3MotionContextSaveLatent: prefix ``h3_context/ep02_u01``
    + clip 1 → ``h3_context/ep02_u01_00001.safetensors``.
    """
    prefix = (filename_prefix or "h3_context/clip").replace("\\", "/").strip("/")
    if "/" in prefix:
        folder, name = prefix.rsplit("/", 1)
    else:
        folder, name = "", prefix
    filename = f"{name}_{int(clip_index):05d}.safetensors"
    return f"{folder}/{filename}" if folder else filename


def extract_saved_latent_path(
    history_entry: dict[str, Any],
    *,
    filename_prefix: str | None = None,
    clip_index: int | None = None,
) -> str | None:
    """Best-effort read of MotionContextSaveLatent STRING output.

    Comfy history often omits STRING-only output-node payloads; fall back to
    the deterministic slot path from prefix + clip_index.
    """
    outputs = history_entry.get("outputs") or {}
    for nid in (NODE_SAVE, NODE_SAVE_PREVIEW):
        payload = outputs.get(nid) or {}
        for key in ("text", "strings", "tags"):
            for item in payload.get(key) or []:
                if isinstance(item, str) and item.strip():
                    return item.strip()
                if isinstance(item, dict):
                    for k in ("text", "string", "path"):
                        if item.get(k):
                            return str(item[k]).strip()
    meta = (history_entry.get("meta") or {}).get(NODE_SAVE) or {}
    if isinstance(meta, dict) and meta.get("latent_path"):
        return str(meta["latent_path"])
    if filename_prefix and clip_index and int(clip_index) > 0:
        return motion_context_slot_relpath(filename_prefix, int(clip_index))
    return None


def preferred_video_node_ids(profile: RenderProfile) -> list[str]:
    if profile.second_pass:
        return [NODE_PASS2_COMBINE, NODE_PASS1_COMBINE]
    return [NODE_PASS1_COMBINE]
