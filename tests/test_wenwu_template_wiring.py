"""Regression: wenwu 265 must be link-fed, never frozen literals.

The yz_h3_wenwu_test API export once lost the links from 263/252/250 into
MiniMaxH3ReferenceToVideo (265), freezing prompt="" / 1344x768 / length 124.
Units then rendered from reference images only, at the wrong duration.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = [
    ROOT / "templates/yz_h3_wenwu_test/workflow_api.json",
    ROOT / "templates/yz_h3_wenwu_test/variants/wuxi/workflow_api.json",
    ROOT / "templates/yz_h3_wenwu_test/variants/wenxi/workflow_api.json",
]
EXPECTED = {"prompt": ["263", 0], "width": ["252", 0],
            "height": ["252", 1], "length": ["250", 1]}


def test_265_inputs_are_links_not_literals():
    for path in WORKFLOWS:
        wf = json.loads(path.read_text(encoding="utf-8"))
        inputs = wf["265"]["inputs"]
        for key, want in EXPECTED.items():
            assert inputs[key] == want, f"{path.name}: 265.{key}={inputs[key]!r}"


def test_wenxi_only_changes_fight_loras():
    base = json.loads(WORKFLOWS[0].read_text(encoding="utf-8"))
    wenxi = json.loads(WORKFLOWS[2].read_text(encoding="utf-8"))
    diffs = {nid for nid in base if base[nid] != wenxi.get(nid)}
    assert diffs == {"342", "343", "345"}
    for nid in diffs:
        assert wenxi[nid]["inputs"]["strength_model"] == 0.0


def test_wuxi_matches_base():
    base = json.loads(WORKFLOWS[0].read_text(encoding="utf-8"))
    wuxi = json.loads(WORKFLOWS[1].read_text(encoding="utf-8"))
    assert base == wuxi
