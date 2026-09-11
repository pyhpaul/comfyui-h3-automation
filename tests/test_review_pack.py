from __future__ import annotations

import re
from pathlib import Path

from comfy_orch.h3_prompt import build_h3_r2v_prompt_review
from comfy_orch.review_pack import find_review_unit_file, parse_review_sections

PACK = Path("/tmp/recompiled-for-review")


def test_parse_review_u01_header():
    text = find_review_unit_file(PACK, "U01").read_text(encoding="utf-8")
    sec = parse_review_sections(text)
    assert sec["unit_id"] == "U01"
    assert sec["title"] == "拔管与抓腕"
    assert sec["duration_seconds"] == "13"


def test_build_h3_r2v_prompt_review_u01():
    text = find_review_unit_file(PACK, "U01").read_text(encoding="utf-8")
    slots = {
        "ref_image_0": "assets/id0-char-001.png",
        "ref_image_1": "assets/id1-char-002-v2.png",
        "ref_image_2": "assets/id2-char-010-nurse.png",
        "ref_image_3": "assets/id3-scene-001.png",
        "ref_image_4": "assets/id4-prop-011-aether-drip-monitor.png",
    }
    out = build_h3_r2v_prompt_review(text, slots)
    assert out.startswith("subject_definitions:")
    assert "<Picture 1>" in out and "<Subject 1>" in out
    assert "[Shot 1]" in out and "[Shot 3]" in out
    assert "Put it back. Now!" in out
    assert "assets/" not in out
    assert not re.search(r"[\u4e00-\u9fff]", out)
