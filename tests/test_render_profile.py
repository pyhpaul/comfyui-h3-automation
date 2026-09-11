from __future__ import annotations

import json
from pathlib import Path

from comfy_orch.render_profile import (
    NODE_MOTION,
    NODE_PASS2_COMBINE,
    NODE_SAVE,
    RenderProfile,
    apply_render_profile,
    preferred_video_node_ids,
)

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "templates" / "yz_h3_ep_unit" / "workflow_api.json"


def test_motion_context_slot_relpath():
    from comfy_orch.render_profile import motion_context_slot_relpath

    assert (
        motion_context_slot_relpath("h3_context/ep02_u01", 1)
        == "h3_context/ep02_u01_00001.safetensors"
    )


def test_extract_falls_back_to_slot_path():
    from comfy_orch.render_profile import extract_saved_latent_path

    assert (
        extract_saved_latent_path(
            {"outputs": {}},
            filename_prefix="h3_context/ep02_u01",
            clip_index=1,
        )
        == "h3_context/ep02_u01_00001.safetensors"
    )


def test_default_profile_is_identity_aside_from_orphan_cleanup():
    raw = json.loads(API.read_text(encoding="utf-8"))
    out = apply_render_profile(raw, RenderProfile())
    assert "328" not in out
    assert NODE_SAVE not in out
    assert NODE_PASS2_COMBINE not in out
    assert "226" in out and "264" in out


def test_motion_latent_u01_saves_without_load():
    raw = json.loads(API.read_text(encoding="utf-8"))
    out = apply_render_profile(
        raw,
        RenderProfile(continuity="motion_latent", save_clip_index=1, load_clip_index=0),
        filename_prefix="EP02-U01",
    )
    assert out[NODE_SAVE]["class_type"] == "MiniMaxH3MotionContextSaveLatent"
    assert NODE_MOTION not in out
    assert "405" in out  # PreviewAny on save path
    assert "ref_videos.ref_video_0" not in out["265"]["inputs"]
    assert "27" not in out
    assert out["264"]["inputs"]["filename_prefix"] == "EP02-U01-pass1"


def test_motion_latent_u02_wires_context_and_second_pass():
    raw = json.loads(API.read_text(encoding="utf-8"))
    out = apply_render_profile(
        raw,
        RenderProfile(
            continuity="motion_latent",
            second_pass=True,
            save_clip_index=2,
            load_clip_index=1,
            motion_latent_path="h3_context/ep02_u01_00001.safetensors",
        ),
        filename_prefix="EP02-U02",
    )
    assert NODE_MOTION in out
    assert out["223"]["inputs"]["conditioning"] == [NODE_MOTION, 0]
    assert out["144"]["inputs"]["guider"] == ["406", 0]
    assert out["406"]["inputs"]["conditioning"] == ["265", 0]
    assert NODE_PASS2_COMBINE in out
    assert out[NODE_PASS2_COMBINE]["inputs"]["filename_prefix"] == "EP02-U02-pass2"
    assert preferred_video_node_ids(RenderProfile(second_pass=True))[0] == NODE_PASS2_COMBINE
