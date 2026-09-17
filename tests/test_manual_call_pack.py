from __future__ import annotations

from pathlib import Path

import pytest

from comfy_orch.errors import ValidationError
from comfy_orch.manual_call_pack import (
    is_h3_manual_call_pack,
    list_manual_unit_ids,
    parse_manual_unit_txt,
    plan_manual_unit,
    wire_manual_model_prompt,
)

PACK = Path("/mnt/c/Users/lxy/Downloads/H3-EP01-EP03-调用包-v3")


@pytest.fixture(scope="module")
def pack_root() -> Path:
    if not PACK.is_dir():
        pytest.skip(f"pack not present: {PACK}")
    return PACK


def test_detects_manual_call_pack(pack_root: Path):
    assert is_h3_manual_call_pack(pack_root) is True


def test_list_ep01_units(pack_root: Path):
    ids = list_manual_unit_ids(pack_root, episode="EP01")
    assert "ep01-s01-c1" in ids
    assert "ep01-s01-c2" in ids
    assert "ep01-s01-c3" in ids
    assert all(u.startswith("ep01-") for u in ids)
    assert len(ids) == 11


def test_parse_s01_c1_drops_pending_control(pack_root: Path):
    parsed = parse_manual_unit_txt(
        (pack_root / "EP01" / "ep01-s01-c1.txt").read_text(encoding="utf-8")
    )
    assert parsed.duration_seconds == 6
    assert [a.asset_id for a in parsed.uploadable] == [
        "char-002",
        "char-005",
        "scene-001",
        "prop-001",
    ]
    assert parsed.dropped_control_ids == ["ctrl-ep01-s01-c1-kf1"]
    assert "@图片5" in parsed.model_prompt
    assert "病弱卧床女孩" in parsed.model_prompt


def test_wire_drops_ctrl_sentence_and_maps_pictures():
    model = (
        "@图片1用于病弱卧床女孩的外貌。@图片2用于护理人员。@图片3用于病房。"
        "@图片4用于以太仪。@图片5用于镜头2的构图与站位。全程不变形。\n"
        "镜头1：…\n"
    )
    wired = wire_manual_model_prompt(
        model,
        uploadable_count=4,
        drop_picture_indices={5},
    )
    assert "@图片" not in wired
    assert "<Picture 1>" in wired and "<Picture 4>" in wired
    assert "<Picture 5>" not in wired
    assert "构图与站位" not in wired
    assert "病弱卧床女孩" in wired


def test_plan_s01_c1(pack_root: Path):
    plan = plan_manual_unit(pack_root, "ep01-s01-c1")
    assert plan.pack_kind == "h3_manual_call"
    assert plan.control is None
    assert plan.previz is None
    assert plan.duration_seconds == 6
    assert len(plan.identities) == 4
    assert plan.identities[0].endswith("char-002-v2.png")


def test_plan_unknown_unit(pack_root: Path):
    with pytest.raises(ValidationError):
        plan_manual_unit(pack_root, "ep99-s01-c1")


def test_build_s01_jobs_wire_only(pack_root: Path, tmp_path: Path):
    from comfy_orch.ep_pack import build_unit_job

    job = build_unit_job(pack_root, "ep01-s01-c1", tmp_path)
    prompt = (job / "assets" / "prompt_h3.txt").read_text(encoding="utf-8")
    assert "<Picture 1>" in prompt
    assert "<Picture 4>" in prompt
    assert "@图片" not in prompt
    assert "构图与站位" not in prompt
    assert "病弱卧床女孩" in prompt
    assert (job / "assets" / "id0-char-002-v2.png").is_file() or any(
        p.name.startswith("id0-") for p in (job / "assets").glob("*.png")
    )
