#!/usr/bin/env python3
"""Convert FaceRefine Auto Select UI JSON to Comfy API prompt format.

Widget field names for FaceRefine / stock nodes are hardcoded from the pack
and common Comfy loaders. Muted nodes (mode==2) are dropped; optional links
into them are omitted.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Widgets that are not link-only, in UI widgets_values order.
WIDGETS: dict[str, list[str]] = {
    "KSamplerSelect": ["sampler_name"],
    "BasicScheduler": ["scheduler", "steps", "denoise"],
    # control_after_generate is UI-only; including it makes /prompt 400.
    "RandomNoise": ["noise_seed"],
    "VAELoader": ["vae_name"],
    "UNETLoader": ["unet_name", "weight_dtype"],
    "CLIPLoader": ["clip_name", "type", "device"],
    "LoraLoaderModelOnly": ["lora_name", "strength_model"],
    "LoadImage": ["image"],
    "H3FaceTrackCrop": [
        "detector", "confidence", "crop_factor", "canvas_width", "canvas_height",
        "canvas_mode", "smooth_window", "size_smooth_window", "smooth_method",
        "size_mode", "identity_track", "identity_threshold", "select",
        "fallback_detector", "fallback_head_frac", "select_index",
        "identity_model", "cut_detection", "cut_threshold", "absent_shots",
        "X", "Y", "frame_index",
    ],
    "H3FaceStitch": [
        "paste_region", "mask_dilation", "feather", "colour_match", "blend",
        "undetected_frames", "feather_scales_with_crop",
    ],
    "H3PerFrameDenoise": [
        "denoise_multiplier_small_face", "denoise_multiplier_large_face",
        "scale_mode", "face_px_small", "face_px_large", "gamma", "smooth_frames",
    ],
    "MiniMaxH3ReferenceToVideo": [
        "prompt", "width", "height", "length", "ref_image_size",
    ],
}


def _norm_path(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("\\", "/")
    return value


def convert_ui_workflow(ui: dict[str, Any], *, drop_muted: bool = True) -> dict[str, Any]:
    nodes = {int(n["id"]): n for n in ui.get("nodes") or []}
    link_by_id = {int(L[0]): L for L in ui.get("links") or []}
    muted = {
        nid for nid, n in nodes.items()
        if drop_muted and n.get("mode") not in (None, 0)
    }
    api: dict[str, Any] = {}
    for nid, node in nodes.items():
        if nid in muted:
            continue
        ct = node.get("type")
        if ct in {"Note", "Reroute"}:
            continue
        inputs: dict[str, Any] = {}
        for inp in node.get("inputs") or []:
            name = inp.get("name")
            link = inp.get("link")
            if link is None or name is None:
                continue
            L = link_by_id.get(int(link))
            if not L:
                continue
            src = int(L[1])
            if src in muted:
                continue
            inputs[name] = [str(src), int(L[2])]

        widgets = node.get("widgets_values")
        if isinstance(widgets, dict):
            # VHS-style dict widgets
            for key, val in widgets.items():
                if key in {"videopreview", "audiopreview"}:
                    continue
                inputs[key] = _norm_path(val)
        elif isinstance(widgets, list):
            names = WIDGETS.get(ct or "", [])
            # LoadImage stores ["file", "image"] — only first is the filename
            if ct == "LoadImage" and widgets:
                inputs["image"] = _norm_path(widgets[0])
            else:
                for idx, name in enumerate(names):
                    if idx >= len(widgets):
                        break
                    # Skip linked widget slots that already have a connection
                    if name in inputs:
                        continue
                    inputs[name] = _norm_path(widgets[idx])

        # Drop UI-only / invalid widget leftovers before API submit.
        inputs.pop("control_after_generate", None)
        if ct == "VHS_LoadVideoPath" and inputs.get("format") in {"None", "none", ""}:
            inputs.pop("format", None)
        api[str(nid)] = {"class_type": ct, "inputs": inputs}
    return api


def rebind_models(
    api: dict[str, Any],
    *,
    unet: str,
    clip: str,
    video_vae: str,
    audio_vae: str,
    lora: str | None,
) -> dict[str, Any]:
    out = json.loads(json.dumps(api))
    for node in out.values():
        ct = node.get("class_type")
        inputs = node.setdefault("inputs", {})
        if ct == "UNETLoader":
            inputs["unet_name"] = unet
        elif ct == "CLIPLoader":
            inputs["clip_name"] = clip
            inputs.setdefault("type", "minimax")
        elif ct == "VAELoader":
            name = str(inputs.get("vae_name") or "")
            if "audio" in name.lower():
                inputs["vae_name"] = audio_vae
            else:
                inputs["vae_name"] = video_vae
        elif ct == "LoraLoaderModelOnly" and lora:
            inputs["lora_name"] = lora
    return out


def bind_media(
    api: dict[str, Any],
    *,
    video: str,
    prompt: str,
    ref_images: dict[str, str] | None = None,
) -> dict[str, Any]:
    """ref_images maps LoadImage node id -> uploaded filename."""
    out = json.loads(json.dumps(api))
    refs = ref_images or {}
    for nid, node in out.items():
        ct = node.get("class_type")
        inputs = node.setdefault("inputs", {})
        if ct == "VHS_LoadVideoPath":
            inputs["video"] = video
            # UI stores the literal string "None"; API wants a real null/omit.
            if inputs.get("format") in {"None", "none", ""}:
                inputs.pop("format", None)
        elif ct == "MiniMaxH3ReferenceToVideo":
            inputs["prompt"] = prompt
            # length/width/height come from track crop; keep or let links override
        elif ct == "LoadImage" and nid in refs:
            inputs["image"] = refs[nid]
        elif ct == "VHS_VideoCombine":
            inputs["filename_prefix"] = "facerefine/ep01_u02"
            inputs["save_output"] = True
        # Strip leftover UI-only widgets that survive conversion.
        inputs.pop("control_after_generate", None)
    return out


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    ui = json.loads(args.ui.read_text(encoding="utf-8"))
    api = convert_ui_workflow(ui)
    args.out.write_text(json.dumps(api, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"nodes={len(api)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
