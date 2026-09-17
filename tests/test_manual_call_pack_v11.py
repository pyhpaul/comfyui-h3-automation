from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from comfy_orch.ep_pack import build_unit_job
from comfy_orch.manual_call_pack import (
    is_h3_manual_call_pack,
    list_manual_unit_ids,
    parse_manual_unit_txt,
    plan_manual_unit,
    wire_manual_model_prompt,
)
from comfy_orch.prompt_wire import _strip_media_tokens, preflight_job_dir

PACK_V11 = Path(
    "/mnt/c/Users/lxy/Downloads/H3-EP01-EP03-调用包-v11-v2_1结构"
    "/H3-EP01-EP03-调用包-v11-v2_1结构"
)


@pytest.fixture(scope="module")
def pack_v11() -> Path:
    if not PACK_V11.is_dir():
        pytest.skip(f"pack not present: {PACK_V11}")
    return PACK_V11


def test_detects_v11_pack(pack_v11: Path):
    assert is_h3_manual_call_pack(pack_v11) is True


def test_list_ep01_has_11_units(pack_v11: Path):
    ids = list_manual_unit_ids(pack_v11, episode="EP01")
    assert len(ids) == 11
    assert ids[0] == "ep01-s01-c1"
    assert ids[-1] == "ep01-s04-c2"


def test_parse_v11_numbered_asset_lines_no_ctrl(pack_v11: Path):
    parsed = parse_manual_unit_txt(
        (pack_v11 / "EP01" / "ep01-s01-c1.txt").read_text(encoding="utf-8")
    )
    assert parsed.duration_seconds == 6
    assert parsed.layout == "v21_constraint_shots"
    assert [a.asset_id for a in parsed.uploadable] == [
        "char-002",
        "char-005",
        "scene-001",
        "prop-001",
    ]
    assert parsed.dropped_control_ids == []
    assert "@图片1" in parsed.model_prompt
    assert "@图片4" in parsed.model_prompt
    assert "【交出状态】" not in parsed.model_prompt
    assert "【H3 latent" not in parsed.model_prompt
    assert "TXT 尾部" not in parsed.model_prompt
    assert "Mia" in parsed.model_prompt
    assert "Nurse" in parsed.model_prompt


def test_wire_preserves_body_except_picture_labels(pack_v11: Path):
    raw = (pack_v11 / "EP01" / "ep01-s01-c2.txt").read_text(encoding="utf-8")
    parsed = parse_manual_unit_txt(raw)
    wired = wire_manual_model_prompt(
        parsed.model_prompt,
        uploadable_count=len(parsed.uploadable),
        drop_picture_indices=set(),
    )
    assert "@图片" not in wired
    for i in range(1, len(parsed.uploadable) + 1):
        assert f"<Picture {i}>" in wired

    def _norm(t: str) -> str:
        lines = [ln.rstrip() for ln in _strip_media_tokens(t).splitlines() if ln.strip()]
        return "\n".join(lines)

    assert _norm(parsed.model_prompt) == _norm(wired)
    assert "（Put it back.）" in wired
    assert "{Put it back.}" not in wired


def test_build_all_ep01_jobs_audit_clean(pack_v11: Path, tmp_path: Path):
    ids = list_manual_unit_ids(pack_v11, episode="EP01")
    for uid in ids:
        plan = plan_manual_unit(pack_v11, uid)
        assert plan.pack_kind == "h3_manual_call"
        assert 1 <= len(plan.identities) <= 6
        job = build_unit_job(pack_v11, uid, tmp_path)
        raw = yaml.safe_load((job / "job.yaml").read_text(encoding="utf-8"))
        refs = {k: v for k, v in raw["fields"].items() if k.startswith("ref_image_")}
        prompt = raw["fields"]["prompt"]
        source = (job / "assets" / "prompt_source.txt").read_text(encoding="utf-8")
        assert "@图片" not in prompt
        assert "【H3 latent" not in prompt
        assert "【交出状态】" not in prompt
        assert "【测试提交规则】" not in prompt
        for i in range(1, len(refs) + 1):
            assert f"<Picture {i}>" in prompt

        def _norm(t: str) -> str:
            return "\n".join(
                ln.rstrip() for ln in _strip_media_tokens(t).splitlines() if ln.strip()
            )

        assert _norm(source) == _norm(prompt)
        for rel in refs.values():
            assert (job / rel).is_file()
        rep = preflight_job_dir(job, require_parent_path=True)
        assert rep["ok"] is True, (uid, rep)
