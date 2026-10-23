"""Frozen Test2 EP02/EP03 topology and one-pass G4 admission rules."""

from __future__ import annotations


UNITS = {
    "EP02": tuple(f"U{number:02d}" for number in range(1, 8)),
    "EP03": tuple(f"U{number:02d}" for number in range(1, 9)),
}
INDEPENDENT = {"EP02": frozenset({"U01", "U02", "U04", "U06"}),
               "EP03": frozenset({"U01"})}
SCENES = {
    "EP02": {"U01": "scene-002", "U02": "scene-003", "U03": "scene-003",
             "U04": "scene-004", "U05": "scene-004", "U06": "scene-002",
             "U07": "scene-002"},
    "EP03": {unit: "scene-002" for unit in UNITS["EP03"]},
}
DURATION_SECONDS = 15.083
FPS = 24


def parent_unit(episode: str, unit: str) -> str | None:
    if episode not in UNITS or unit not in UNITS[episode]:
        raise ValueError(f"unexpected Test2 unit: {episode} {unit}")
    return None if unit in INDEPENDENT[episode] else f"U{int(unit[1:]) - 1:02d}"


def job_name(episode: str, unit: str) -> str:
    parent_unit(episode, unit)
    version = "v2" if episode == "EP02" else "v1"
    return f"{episode}-test2-{version}-{unit}"


def validate_job(raw: dict, episode: str, unit: str) -> None:
    parent = parent_unit(episode, unit)
    fields = raw.get("fields") or {}
    refs = [value for key, value in fields.items() if key.startswith("ref_image_")]
    version = "v2" if episode == "EP02" else "v1"
    if (
        raw.get("template") != "yz_h3_ep_unit"
        or raw.get("episode") != episode
        or raw.get("unit_id") != unit
        or raw.get("parent_unit_id") != parent
        or raw.get("start_mode") != ("independent" if parent is None else "parent_latent")
        or float(fields.get("duration_seconds", 0)) != DURATION_SECONDS
        or fields.get("aspect_ratio") != "9:16 (Portrait Widescreen)"
        or float(fields.get("megapixels", 0)) != 1.0
        or not str(fields.get("filename_prefix", "")).startswith(
            f"{episode}-{unit}-test2-{version}")
        or not 1 <= len(refs) <= 9
        or not any(SCENES[episode][unit] in str(value) for value in refs)
        or "ref_video_0" in fields
    ):
        raise RuntimeError(f"{episode} {unit} frozen job mismatch")


def validate_graph(graph: dict, episode: str, unit: str,
                   parent_path: str | None, ref_count: int) -> None:
    expected_parent = parent_unit(episode, unit)
    number = int(unit[1:])
    if (
        not {"58", "128", "259", "264", "265", "289", "400"}.issubset(graph)
        or graph["58"].get("class_type") != "MiniMaxH3MemoryEfficientSageAttentionPatch"
        or graph["58"].get("inputs") != {"model": ["192", 0]}
        or graph["128"]["inputs"].get("model") != ["58", 0]
        or graph["289"]["inputs"].get("step") != 12
        or float(graph["259"]["inputs"].get("value", 0)) != DURATION_SECONDS
        or graph["264"]["inputs"].get("frame_rate") != FPS
        or graph["400"].get("class_type") != "MiniMaxH3MotionContextSaveLatent"
        or graph["400"]["inputs"].get("clip_index") != number
        or graph["400"]["inputs"].get("filename_prefix")
        != f"h3_context/{episode.lower()}_u{number:02d}"
        or any(key.startswith("ref_videos.") for key in graph["265"]["inputs"])
        or "214" in graph
    ):
        raise RuntimeError(f"{episode} {unit} graph changed from one-pass G4 baseline")
    image_inputs = {key for key in graph["265"]["inputs"]
                    if key.startswith("ref_images.")}
    if image_inputs != {f"ref_images.ref_image_{number}" for number in range(ref_count)}:
        raise RuntimeError(f"{episode} {unit} graph image count/order mismatch")
    if expected_parent is None:
        if parent_path is not None or any(node in graph for node in ("401", "402", "403")):
            raise RuntimeError(f"{episode} {unit} independent start loads a latent")
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
        raise RuntimeError(f"{episode} {unit} parent latent/trim edge mismatch")
