from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

# UI node ids in the original YZ layout (Set/Get 图像1..6 / 参考视频1 / 提示词).
# Same semantic slots as API bindings ref_image_0..5 + ref_video_0.
YZ_UI_MEDIA_NODES: dict[str, int] = {
    "ref_image_0": 51,  # 图像1
    "ref_image_1": 49,  # 图像2
    "ref_image_2": 50,  # 图像3
    "ref_image_3": 43,  # 图像4
    "ref_image_4": 19,  # 图像5
    "ref_image_5": 23,  # 图像6
    "ref_video_0": 27,  # 参考视频1
}
# YZ template has up to 3 video slots; EP packs usually only previz → ref_video_0.
YZ_UI_EXTRA_VIDEO_NODES: dict[str, int] = {
    "ref_video_1": 25,  # 参考视频2
    "ref_video_2": 26,  # 参考视频3
}
YZ_UI_PROMPT_NODE = 263
YZ_UI_DURATION_NODE = 259
YZ_UI_ASPECT_NODE = 252
YZ_UI_OUTPUT_COMBINE_NODE = 264  # VHS_VideoCombine 一采 / API title YZ成片输出
YZ_UI_OUTPUT2_COMBINE_NODE = 214  # VHS_VideoCombine 二采（若存在，同步前缀便于对照）
# Original YZ has 3 LoadAudio slots (参考音频1..3); EP packs usually have none.
YZ_UI_AUDIO_NODES: dict[str, int] = {
    "ref_audio_0": 48,  # 参考音频1
    "ref_audio_1": 14,  # 参考音频2
    "ref_audio_2": 15,  # 参考音频3
}
YZ_UI_H3_NODE = 265
# LiteGraph / Comfy: 0=Always, 2=Never, 4=Bypass
NODE_MODE_NEVER = 2


def _disconnect_h3_inputs(ui: dict[str, Any], *, prefixes: tuple[str, ...]) -> None:
    by_id = {n["id"]: n for n in ui.get("nodes") or []}
    h3 = by_id.get(YZ_UI_H3_NODE)
    if h3 is None:
        return
    drop_ids: set[int] = set()
    for inp in h3.get("inputs") or []:
        name = inp.get("name") or ""
        if any(name.startswith(p) for p in prefixes):
            lid = inp.get("link")
            if lid is not None:
                drop_ids.add(int(lid))
            inp["link"] = None
    if not drop_ids:
        return
    ui["links"] = [L for L in (ui.get("links") or []) if int(L[0]) not in drop_ids]
    for node in ui.get("nodes") or []:
        for out in node.get("outputs") or []:
            links = out.get("links")
            if not links:
                continue
            out["links"] = [x for x in links if int(x) not in drop_ids]


def _disconnect_h3_ref_audios(ui: dict[str, Any]) -> None:
    _disconnect_h3_inputs(ui, prefixes=("ref_audios.",))


def _mute_unused_video_slots(ui: dict[str, Any], *, values: dict[str, Any]) -> None:
    """Keep only previz (and any explicit extra videos); mute the rest."""
    by_id = {n["id"]: n for n in ui.get("nodes") or []}
    unused: list[str] = []
    for field, nid in YZ_UI_EXTRA_VIDEO_NODES.items():
        if field in values:
            continue
        unused.append(field)
        node = by_id.get(nid)
        if node is not None and node.get("type") == "VHS_LoadVideo":
            node["mode"] = NODE_MODE_NEVER
            wv = dict(node.get("widgets_values") or {})
            wv["video"] = ""
            wv["videopreview"] = {
                "paused": False,
                "hidden": True,
                "params": {},
            }
            node["widgets_values"] = wv
    if not unused:
        return
    want = {f"ref_videos.{f}" for f in unused}
    h3 = by_id.get(YZ_UI_H3_NODE)
    if h3 is None:
        return
    drop_ids: set[int] = set()
    for inp in h3.get("inputs") or []:
        if inp.get("name") in want:
            lid = inp.get("link")
            if lid is not None:
                drop_ids.add(int(lid))
            inp["link"] = None
    if not drop_ids:
        return
    ui["links"] = [L for L in (ui.get("links") or []) if int(L[0]) not in drop_ids]
    for node in ui.get("nodes") or []:
        for out in node.get("outputs") or []:
            links = out.get("links")
            if not links:
                continue
            out["links"] = [x for x in links if int(x) not in drop_ids]


def _mute_unused_image_slots(ui: dict[str, Any], *, values: dict[str, Any]) -> None:
    """Only keep LoadImage slots present in values; mute + disconnect the rest."""
    by_id = {n["id"]: n for n in ui.get("nodes") or []}
    unused_fields: list[str] = []
    for field, nid in YZ_UI_MEDIA_NODES.items():
        if not field.startswith("ref_image_"):
            continue
        if field in values:
            continue
        unused_fields.append(field)
        node = by_id.get(nid)
        if node is not None and node.get("type") == "LoadImage":
            node["mode"] = NODE_MODE_NEVER
            wv = list(node.get("widgets_values") or ["None", "image"])
            wv[0] = "None"
            node["widgets_values"] = wv
    if unused_fields:
        # Disconnect matching H3 ports, e.g. ref_images.ref_image_4
        indices = [f.split("_")[-1] for f in unused_fields]
        prefixes = tuple(f"ref_images.ref_image_{i}" for i in indices)
        # startswith needs unique prefixes; use exact name match via custom loop
        h3 = by_id.get(YZ_UI_H3_NODE)
        if h3 is None:
            return
        drop_ids: set[int] = set()
        want = {f"ref_images.ref_image_{i}" for i in indices}
        for inp in h3.get("inputs") or []:
            if inp.get("name") in want:
                lid = inp.get("link")
                if lid is not None:
                    drop_ids.add(int(lid))
                inp["link"] = None
        if drop_ids:
            ui["links"] = [L for L in (ui.get("links") or []) if int(L[0]) not in drop_ids]
            for node in ui.get("nodes") or []:
                for out in node.get("outputs") or []:
                    links = out.get("links")
                    if not links:
                        continue
                    out["links"] = [x for x in links if int(x) not in drop_ids]


def _is_placeholder_audio(name: str) -> bool:
    lower = name.lower()
    return lower.startswith("silent") or lower in {"", "none"}


def apply_values_to_ui_workflow(
    ui_workflow: dict[str, Any],
    *,
    values: dict[str, Any],
    disable_placeholder_audio: bool = True,
) -> dict[str, Any]:
    """Patch widget values on a Comfy UI-format graph; keep pos/links/groups."""
    out = copy.deepcopy(ui_workflow)
    by_id = {n["id"]: n for n in out.get("nodes") or []}

    for field, nid in YZ_UI_MEDIA_NODES.items():
        if field not in values:
            continue
        node = by_id.get(nid)
        if node is None:
            raise KeyError(f"UI node {nid} missing for {field}")
        name = str(values[field])
        if node.get("type") == "LoadImage":
            wv = list(node.get("widgets_values") or ["", "image"])
            wv[0] = name
            if len(wv) < 2:
                wv.append("image")
            node["widgets_values"] = wv
        elif node.get("type") == "VHS_LoadVideo":
            wv = dict(node.get("widgets_values") or {})
            wv["video"] = name
            # VHS preview only refreshes from videopreview.params; video alone
            # leaves a stale thumbnail after Load.
            ext = Path(name).suffix.lstrip(".").lower() or "webm"
            fmt = f"image/{ext}" if ext in {"gif", "webp", "avif"} else f"video/{ext}"
            wv["videopreview"] = {
                "paused": False,
                "hidden": False,
                "params": {
                    "filename": name,
                    "type": "input",
                    "format": fmt,
                },
            }
            node["widgets_values"] = wv
        else:
            raise TypeError(f"unsupported media node type: {node.get('type')}")

    for field, nid in YZ_UI_AUDIO_NODES.items():
        if field not in values:
            continue
        node = by_id.get(nid)
        if node is None:
            raise KeyError(f"UI node {nid} missing for {field}")
        if node.get("type") != "LoadAudio":
            raise TypeError(f"expected LoadAudio at {nid}, got {node.get('type')}")
        wv = list(node.get("widgets_values") or ["None", None, None])
        wv[0] = str(values[field])
        while len(wv) < 3:
            wv.append(None)
        node["widgets_values"] = wv

    # EP packs have no story audio. Frontend flags empty LoadAudio as blocking errors;
    # mute those nodes and disconnect H3 ref_audios when only placeholders are present.
    audio_vals = [str(values[k]) for k in YZ_UI_AUDIO_NODES if k in values]
    if disable_placeholder_audio and (
        not audio_vals or all(_is_placeholder_audio(v) for v in audio_vals)
    ):
        _disconnect_h3_ref_audios(out)
        by_id = {n["id"]: n for n in out.get("nodes") or []}
        for nid in YZ_UI_AUDIO_NODES.values():
            node = by_id.get(nid)
            if node is not None:
                node["mode"] = NODE_MODE_NEVER

    _mute_unused_image_slots(out, values=values)
    _mute_unused_video_slots(out, values=values)

    by_id = {n["id"]: n for n in out.get("nodes") or []}
    if "prompt" in values and YZ_UI_PROMPT_NODE in by_id:
        node = by_id[YZ_UI_PROMPT_NODE]
        node["widgets_values"] = [str(values["prompt"])]

    if "duration_seconds" in values and YZ_UI_DURATION_NODE in by_id:
        node = by_id[YZ_UI_DURATION_NODE]
        node["widgets_values"] = [values["duration_seconds"]]

    if "aspect_ratio" in values and YZ_UI_ASPECT_NODE in by_id:
        node = by_id[YZ_UI_ASPECT_NODE]
        wv = list(node.get("widgets_values") or ["16:9 (Widescreen)", 1.0, 32])
        wv[0] = str(values["aspect_ratio"])
        if "megapixels" in values:
            wv[1] = float(values["megapixels"])
        node["widgets_values"] = wv
    elif "megapixels" in values and YZ_UI_ASPECT_NODE in by_id:
        node = by_id[YZ_UI_ASPECT_NODE]
        wv = list(node.get("widgets_values") or ["16:9 (Widescreen)", 1.0, 32])
        wv[1] = float(values["megapixels"])
        node["widgets_values"] = wv

    if "filename_prefix" in values:
        prefix = str(values["filename_prefix"])
        for nid in (YZ_UI_OUTPUT_COMBINE_NODE, YZ_UI_OUTPUT2_COMBINE_NODE):
            node = by_id.get(nid)
            if node is None or node.get("type") != "VHS_VideoCombine":
                continue
            wv = node.get("widgets_values")
            if isinstance(wv, dict):
                wv = dict(wv)
                wv["filename_prefix"] = prefix
                node["widgets_values"] = wv
            elif isinstance(wv, list):
                # rare list layout — leave untouched if structure unknown
                pass

    return out


def export_bound_ui_workflow(
    *,
    ui_workflow_path: Path,
    values: dict[str, Any],
    out_path: Path,
) -> Path:
    ui = json.loads(ui_workflow_path.read_text(encoding="utf-8"))
    bound = apply_values_to_ui_workflow(ui, values=values)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(bound, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return out_path


def prune_unused_api_ref_images(
    workflow: dict[str, Any],
    *,
    values: dict[str, Any],
) -> dict[str, Any]:
    """Drop H3 ref_images / unused ref_videos inputs that have no job field."""
    out = copy.deepcopy(workflow)
    h3 = out.get("265")
    if not isinstance(h3, dict):
        return out
    inputs = dict(h3.get("inputs") or {})
    for i in range(0, 9):
        field = f"ref_image_{i}"
        key = f"ref_images.ref_image_{i}"
        if field not in values and key in inputs:
            del inputs[key]
    for i in range(0, 3):
        field = f"ref_video_{i}"
        key = f"ref_videos.ref_video_{i}"
        if field not in values and key in inputs:
            del inputs[key]
    h3["inputs"] = inputs
    return out
