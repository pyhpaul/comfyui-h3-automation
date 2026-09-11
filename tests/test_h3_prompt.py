from __future__ import annotations

import re
from pathlib import Path

from comfy_orch.h3_prompt import build_h3_r2v_prompt
from comfy_orch.ep_pack import map_yz_media_slots


FIXTURES = Path(__file__).parent / "fixtures"
EP_U01 = Path("/tmp/ep02_assets/EP03/prompts/U01.txt")
GOLD = FIXTURES / "ep03_u01_h3_gold.txt"

SECTION_HEADERS = (
    "subject_definitions:",
    "summary:",
    "retention_analysis:",
    "detailed_description:",
    "overall_soundscape:",
    "non_diegetic_music:",
)


def _u01_slots() -> dict[str, str]:
    return map_yz_media_slots(
        control="control/U01-director-control.png",
        previz="previz/U01-colour-blockout.webm",
        identities=[
            "assets/characters/char-001.png",
            "assets/characters/char-009-v2-toxic-duty-guard.png",
            "assets/scenes/scene-010.png",
        ],
    )


def test_build_h3_r2v_prompt_six_sections_and_labels():
    ep = EP_U01.read_text(encoding="utf-8")
    out = build_h3_r2v_prompt(ep, _u01_slots())
    for header in SECTION_HEADERS:
        assert header in out
    assert "<Picture 1>" in out
    assert "storyboard" in out.lower() or "director-control" in out.lower()
    assert "<Subject 1>" in out and "<Picture 2>" in out
    assert "<Subject 2>" in out and "<Picture 3>" in out
    assert "<Subject 3>" in out and "<Picture 4>" in out
    assert "<Video 1>" in out
    assert "non_diegetic_music:\nN/A" in out or "non_diegetic_music:\nN/A\n" in out
    assert "assets/" not in out
    assert "【本 U 实际上传顺序】" not in out
    assert "@previz" not in out


def test_build_h3_r2v_prompt_shares_gold_structure():
    ep = EP_U01.read_text(encoding="utf-8")
    out = build_h3_r2v_prompt(ep, _u01_slots())
    gold = GOLD.read_text(encoding="utf-8")
    for header in SECTION_HEADERS:
        assert header in out and header in gold
    for token in (
        "<Picture 1>",
        "<Picture 2>",
        "<Picture 3>",
        "<Picture 4>",
        "<Video 1>",
        "<Subject 1>",
        "<Subject 2>",
        "<Subject 3>",
        "[Shot 1]",
        "[Shot 2]",
        "[Shot 3]",
        "fully_preserved",
        "N/A",
    ):
        assert token in out
        assert token in gold


def test_build_h3_r2v_prompt_wiring_aligned_english():
    """YZ slots: control=Picture1, identities=Picture2+, previz=Video1; English body."""
    ep = EP_U01.read_text(encoding="utf-8")
    out = build_h3_r2v_prompt(ep, _u01_slots())
    assert "comes from <Picture 2>" in out
    assert "comes from <Picture 3>" in out
    assert "comes from <Picture 4>" in out
    assert "storyboard" in out.lower() or "director-control" in out.lower()
    assert "@char-" not in out
    assert "@control" not in out
    assert "@previz" not in out
    assert "assets/" not in out
    assert not re.search(r"[\u4e00-\u9fff]", out), "H3 body must be English (CJK left over)"
    assert "<Subject 1>" in out and "<Subject 2>" in out
    detail = out.split("detailed_description:", 1)[1]
    assert "[Shot 1]" in detail
    shot1 = detail.split("[Shot 1]", 1)[1].split("[Shot 2]", 1)[0]
    assert "<Subject 1>" in shot1 and "<Subject 2>" in shot1
