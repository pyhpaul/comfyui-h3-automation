from __future__ import annotations

import re
from pathlib import Path

from comfy_orch.causality_pack import (
    is_ep02_causality_pack,
    list_causality_unit_ids,
    plan_causality_unit,
)
from comfy_orch.ep_pack import build_unit_job
from comfy_orch.h3_prompt import build_h3_r2v_prompt_causality

PACK = Path("/tmp/EP02-H3-physical-causality-test-v2_1-20260910")


def test_detect_and_list_units():
    assert is_ep02_causality_pack(PACK)
    assert list_causality_unit_ids(PACK) == [f"U{i:02d}" for i in range(1, 8)]


def test_plan_u01_assets():
    plan = plan_causality_unit(PACK, "U01")
    assert plan.pack_kind == "ep02_causality"
    assert plan.duration_seconds == 9
    assert plan.control is None and plan.previz is None
    assert len(plan.identities) == 5
    assert all((PACK / p).is_file() for p in plan.identities)
    assert plan.identities[0].endswith("char-001.png")


def test_prompt_causality_u01(tmp_path: Path):
    job = build_unit_job(PACK, "U01", tmp_path)
    prompt = (job / "assets" / "prompt_h3.txt").read_text(encoding="utf-8")
    assert "<Picture 1>" in prompt
    assert "【镜头1" in prompt or "镜头1" in prompt
    assert "You little bastard" in prompt
    assert "E:\\" not in prompt
    assert "诱兽" in prompt or "潜伏兽" in prompt
    assert "subject_definitions:" not in prompt
    assert (job / "job.yaml").is_file()
