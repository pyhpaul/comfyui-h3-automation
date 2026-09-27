"""Frozen Test2 EP01 job and G4 graph gates."""

from __future__ import annotations


UNITS = tuple(f"U{number:02d}" for number in range(1, 9))
PARENTS = {
    unit: (None if unit in {"U01", "U05"} else f"U{int(unit[1:]) - 1:02d}")
    for unit in UNITS
}
DURATION_SECONDS = 15.083
FPS = 24
SCENES = {unit: ("scene-001" if unit <= "U04" else "scene-002") for unit in UNITS}


def job_name(unit: str) -> str:
    if unit not in PARENTS:
        raise ValueError(f"unexpected Test2 EP01 unit: {unit}")
    suffix = "-independent-candidate" if unit == "U05" else ""
    return f"EP01-测试2-v1-{unit}{suffix}"


def validate_job(raw: dict, unit: str) -> None:
    if unit not in PARENTS:
        raise RuntimeError(f"unexpected Test2 EP01 unit: {unit}")
    fields = raw.get("fields") or {}
    refs = [value for key, value in fields.items() if key.startswith("ref_image_")]
    expected_prefix = f"EP01-{unit}-test2"
    if (
        raw.get("template") != "yz_h3_ep_unit"
        or raw.get("unit_id") != unit
        or raw.get("parent_unit_id") != PARENTS[unit]
        or float(fields.get("duration_seconds", 0)) != DURATION_SECONDS
        or fields.get("aspect_ratio") != "9:16 (Portrait Widescreen)"
        or float(fields.get("megapixels", 0)) != 1.0
        or not str(fields.get("filename_prefix", "")).startswith(expected_prefix)
        or not 1 <= len(refs) <= 9
        or not any(SCENES[unit] in str(value) for value in refs)
        or "ref_video_0" in fields
    ):
        raise RuntimeError(f"{unit} frozen Test2 job mismatch")
    if unit == "U05" and raw.get("start_mode") != "independent":
        raise RuntimeError("U05 must be the approved independent-start candidate")


def validate_graph(graph: dict, unit: str, parent_path: str | None) -> None:
    if unit not in PARENTS:
        raise RuntimeError(f"unexpected Test2 EP01 unit: {unit}")
    expected_parent = PARENTS[unit]
    number = int(unit[1:])
    required = {"58", "128", "259", "264", "265", "289", "400"}
    if (
        not required.issubset(graph)
        or graph["58"].get("class_type") != "MiniMaxH3MemoryEfficientSageAttentionPatch"
        or graph["58"].get("inputs") != {"model": ["192", 0]}
        or graph["128"]["inputs"].get("model") != ["58", 0]
        or graph["289"]["inputs"].get("step") != 12
        or float(graph["259"]["inputs"].get("value", 0)) != DURATION_SECONDS
        or graph["264"]["inputs"].get("frame_rate") != FPS
        or graph["400"].get("class_type") != "MiniMaxH3MotionContextSaveLatent"
        or graph["400"]["inputs"].get("clip_index") != number
        or graph["400"]["inputs"].get("filename_prefix")
        != f"h3_context/ep01_u{number:02d}"
        or any(key.startswith("ref_videos.") for key in graph["265"]["inputs"])
        or "214" in graph
    ):
        raise RuntimeError(f"{unit} graph changed from approved one-pass G4 profile")
    if expected_parent is None:
        if parent_path is not None or any(node in graph for node in ("401", "402", "403")):
            raise RuntimeError(f"{unit} independent start loads a parent latent")
        return
    if (
        not parent_path
        or graph.get("401", {}).get("class_type") != "MiniMaxH3MotionContextLoadLatent"
        or graph["401"]["inputs"]
        != {"latent_path": parent_path, "clip_index": int(expected_parent[1:])}
        or graph.get("402", {}).get("class_type") != "MiniMaxH3MotionContext"
        or graph["402"]["inputs"].get("context_length") != "22"
        or graph["402"]["inputs"].get("audio_context_length") != 24
        or graph.get("403", {}).get("class_type") != "MiniMaxH3MotionContextTrim"
        or graph["403"]["inputs"].get("fps") != 24.0
        or graph["403"]["inputs"].get("match_tail") is not True
        or graph["264"]["inputs"].get("images") != ["403", 0]
        or graph["264"]["inputs"].get("audio") != ["403", 1]
    ):
        raise RuntimeError(f"{unit} is not loading and trimming its verified parent latent")
