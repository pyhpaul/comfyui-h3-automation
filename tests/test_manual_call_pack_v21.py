from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from comfy_orch.ep_pack import build_unit_job
from comfy_orch.manual_call_pack import (
    is_h3_manual_call_pack,
    parse_manual_unit_txt,
    plan_manual_unit,
)
from comfy_orch.prompt_wire import preflight_job_dir

PACK_V21 = Path("/mnt/c/Users/lxy/Downloads/H3-EP01-EP03-调用包-v8-v2_1结构")


@pytest.fixture(scope="module")
def pack_v21() -> Path:
    if not PACK_V21.is_dir():
        pytest.skip(f"pack not present: {PACK_V21}")
    return PACK_V21


def test_detects_v21_pack(pack_v21: Path):
    assert is_h3_manual_call_pack(pack_v21) is True


def test_parse_v21_s01_c1_keeps_control_and_model_body(pack_v21: Path):
    parsed = parse_manual_unit_txt(
        (pack_v21 / "EP01" / "ep01-s01-c1.txt").read_text(encoding="utf-8")
    )
    assert parsed.duration_seconds == 6
    assert [a.asset_id for a in parsed.uploadable] == [
        "char-002",
        "char-005",
        "scene-001",
        "prop-001",
        "ctrl-ep01-s01-c1-kf1",
    ]
    assert parsed.dropped_control_ids == []
    assert "@图片1" in parsed.model_prompt
    assert "@图片5" in parsed.model_prompt
    assert "【镜头1｜" in parsed.model_prompt or "【镜头1|" in parsed.model_prompt
    assert "【交出状态】" not in parsed.model_prompt
    assert "【H3 latent" not in parsed.model_prompt
    assert "【测试提交规则】" not in parsed.model_prompt
    assert "禁止朗读" in parsed.model_prompt
    assert "〔" not in parsed.model_prompt


def test_parse_v21_s01_c2_dialogue_fullwidth_parens(pack_v21: Path):
    parsed = parse_manual_unit_txt(
        (pack_v21 / "EP01" / "ep01-s01-c2.txt").read_text(encoding="utf-8")
    )
    assert parsed.duration_seconds == 9
    assert len(parsed.uploadable) == 6
    assert parsed.uploadable[-1].asset_id.startswith("ctrl-")
    assert "（Put it back.）" in parsed.model_prompt
    assert "{Put it back.}" not in parsed.model_prompt


def test_plan_and_build_v21_s01_units(pack_v21: Path, tmp_path: Path):
    for uid, n_img in (("ep01-s01-c1", 5), ("ep01-s01-c2", 6), ("ep01-s01-c3", 6)):
        plan = plan_manual_unit(pack_v21, uid)
        assert plan.pack_kind == "h3_manual_call"
        assert len(plan.identities) == n_img
        job = build_unit_job(pack_v21, uid, tmp_path)
        raw = yaml.safe_load((job / "job.yaml").read_text(encoding="utf-8"))
        refs = {k: v for k, v in raw["fields"].items() if k.startswith("ref_image_")}
        assert len(refs) == n_img
        prompt = raw["fields"]["prompt"]
        assert "@图片" not in prompt
        for i in range(1, n_img + 1):
            assert f"<Picture {i}>" in prompt
        assert "【测试提交规则】" not in prompt
        assert "【H3 latent" not in prompt
        for rel in refs.values():
            assert (job / rel).is_file()
        rep = preflight_job_dir(job, require_parent_path=True)
        assert rep["ok"] is True, rep
