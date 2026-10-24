"""fix_fail_router classification + ban same-prompt ×3."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))

from fix_fail_router import route_registry  # noqa: E402


def test_three_fails_class_a_bans_retry():
    data = {
        "slots": {"EP45-U01:wenxi": "pending"},
        "candidates": [
            {"unit": "EP45-U01", "chain": "wenxi", "tag": "C1", "verdict": "fail"},
            {"unit": "EP45-U01", "chain": "wenxi", "tag": "C2", "verdict": "fail"},
            {"unit": "EP45-U01", "chain": "wenxi", "tag": "C3", "verdict": "fail"},
        ],
    }
    report = route_registry(data, {"EP45-U01": "FAIL U01（片头胡话）"})
    assert len(report["routes"]) == 1
    r = report["routes"][0]
    assert r["class"] == "A"
    assert r["ban_same_prompt_x3"] is True
    assert r["max_new_seeds_after_fix"] == 0


def test_silent_unit_routes_to_b():
    data = {
        "slots": {},
        "candidates": [
            {"unit": "EP11-U04", "chain": "wenxi", "tag": "C1", "verdict": "fail"},
            {"unit": "EP11-U04", "chain": "wenxi", "tag": "C2", "verdict": "fail"},
            {"unit": "EP11-U04", "chain": "wenxi", "tag": "C3", "verdict": "fail"},
        ],
    }
    report = route_registry(data, {"EP11-U04": "无对白条全程胡话"})
    assert report["routes"][0]["class"] == "B"
    assert "closed_mouth" in report["routes"][0]["action"]
