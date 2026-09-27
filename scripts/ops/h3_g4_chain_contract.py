"""Frozen one-pass graph and job checks for the EP04 G4 continuation chain."""

from __future__ import annotations


def validate_graph(graph: dict, unit: str, parent: str) -> None:
    number = int(unit[1:])
    required = {"58", "128", "264", "289", "400", "401"}
    if not required.issubset(graph):
        raise RuntimeError("missing frozen H3 graph nodes")
    if (graph["58"].get("class_type") != "MiniMaxH3MemoryEfficientSageAttentionPatch"
            or graph["58"].get("inputs") != {"model": ["192", 0]}
            or graph["128"]["inputs"].get("model") != ["58", 0]
            or graph["289"]["inputs"].get("step") != 12
            or graph["264"]["inputs"].get("frame_rate") != 24
            or graph["401"].get("class_type") != "MiniMaxH3MotionContextLoadLatent"
            or graph["401"]["inputs"] != {"latent_path": parent, "clip_index": number - 1}
            or graph["400"].get("class_type") != "MiniMaxH3MotionContextSaveLatent"
            or graph["400"]["inputs"].get("clip_index") != number
            or graph["400"]["inputs"].get("filename_prefix") != f"h3_context/ep04_u{number:02d}"):
        raise RuntimeError(f"{unit} graph changed from the approved one-pass G4 profile")


def validate_job(raw: dict, unit: str) -> None:
    number = int(unit[1:])
    if (raw.get("unit_id") != unit or raw.get("parent_unit_id") != f"U{number - 1:02d}"
            or raw.get("template") != "yz_h3_ep_unit"
            or raw.get("fields", {}).get("filename_prefix") != f"EP04-{unit}-v16"):
        raise RuntimeError(f"{unit} frozen job contract mismatch")
