"""Pilot QC gates: L2 hard close + L3 denser overview fps + triage."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_l2_required_blocks_close_when_watch_incomplete(tmp_path: Path, monkeypatch):
    plan_mod = _load("post_local_pilot_qc_gate", "scripts/ops/post_local_pilot_qc.py")
    monkeypatch.setattr(plan_mod, "ROOT", tmp_path)
    out = tmp_path / "out"
    unit_dir = out / "EP43-U06" / "S01" / "cand"
    unit_dir.mkdir(parents=True)
    (unit_dir / "x.mp4").write_bytes(b"fake")
    (unit_dir / "dialogue_check.json").write_text(
        json.dumps({"ok": True, "reason": "OK", "overlap": 1.0}), encoding="utf-8"
    )
    (unit_dir / "l2_status.json").write_text(
        json.dumps({"status": "WATCH_INCOMPLETE", "unit": "EP43-U06"}),
        encoding="utf-8",
    )
    job = tmp_path / "jobs" / "EP43"
    (job / "assets").mkdir(parents=True)
    (job / "assets" / "prompt_source.txt").write_text(
        "双人同框：说话者开口；听者与画内其他人全程闭口无声，禁止同念。\n"
        "说：（ Hello. ）\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(plan_mod, "_JOB", {"EP43-U06": job})

    plan = plan_mod.build_plan("test-batch", out)
    unit = next(u for u in plan["units"] if u["unit"] == "EP43-U06")
    assert unit["L2_required"] is True
    assert unit["L2_status"] == "WATCH_INCOMPLETE"
    assert plan_mod.l2_blocks_close(plan) is True


def test_l2_done_allows_close(tmp_path: Path, monkeypatch):
    plan_mod = _load("post_local_pilot_qc_gate2", "scripts/ops/post_local_pilot_qc.py")
    monkeypatch.setattr(plan_mod, "ROOT", tmp_path)
    out = tmp_path / "out"
    unit_dir = out / "EP43-U06" / "S01" / "cand"
    unit_dir.mkdir(parents=True)
    (unit_dir / "x.mp4").write_bytes(b"x")
    (unit_dir / "dialogue_check.json").write_text(
        json.dumps({"ok": True, "reason": "OK"}), encoding="utf-8"
    )
    (unit_dir / "l2_status.json").write_text(
        json.dumps({"status": "DONE", "verdict": "PASS"}), encoding="utf-8"
    )
    job = tmp_path / "jobs" / "EP43"
    (job / "assets").mkdir(parents=True)
    (job / "assets" / "prompt_source.txt").write_text("说：（ Hello. ）\n", encoding="utf-8")
    monkeypatch.setattr(plan_mod, "_JOB", {"EP43-U06": job})
    plan = plan_mod.build_plan("b", out)
    assert plan_mod.l2_blocks_close(plan) is False


def test_l3_default_overview_fps_is_dense():
    l3 = _load("pilot_l3_blooper_screen_gate", "scripts/ops/pilot_l3_blooper_screen.py")
    assert l3.OVERVIEW_FPS >= 2.0
    assert "假阳性" in l3.FALSE_POSITIVE_HINT or "false" in l3.FALSE_POSITIVE_HINT.lower()


def test_l3_triage_scores_gross_chaos_high():
    l3 = _load("pilot_l3_blooper_screen_triage", "scripts/ops/pilot_l3_blooper_screen.py")
    assert l3.score_triage([]) == "NONE"
    assert l3.score_triage([{"category": "extra_limb"}]) == "HIGH"
    assert l3.score_triage([{"category": "other"}]) == "LOW"
    assert l3.score_triage(
        [{"category": "prop_continuity"}, {"category": "wardrobe_continuity"}]
    ) == "MED"
    # Model raise allowed; heuristic floor kept when model lower
    assert l3.score_triage([{"category": "other"}], "HIGH") == "HIGH"
    assert l3.score_triage([{"category": "extra_limb"}], "LOW") == "HIGH"


def test_l3_unknown_frame_ids_softened_not_hard_fail():
    l3 = _load("pilot_l3_blooper_screen_soft", "scripts/ops/pilot_l3_blooper_screen.py")
    answer = {
        "unit": "EP11-U04",
        "suspects": [
            {
                "id": "S1",
                "category": "extra_limb",
                "frame_ids": ["F001", "ov:sheet1"],
                "detail_frame_ids": ["dn:mid"],
                "observed": "extra hand",
            }
        ],
        "detail_frame_ids": ["F002", "bogus"],
        "visible_events": [],
        "mouth_visibility_notes": [],
        "limitations": [],
    }
    warnings = l3.sanitize_answer_frame_ids(answer, {"F001", "F002"})
    assert warnings
    assert answer["suspects"][0]["frame_ids"] == ["F001"]
    assert "ov:sheet1" in answer["suspects"][0]["nav_hints"]
    assert answer["detail_frame_ids"] == ["F002"]
    confirm = l3.build_confirm(answer, "EP11-U04", Path("/tmp/c"), triage_risk="HIGH")
    assert confirm["triage_risk"] == "HIGH"
    assert confirm["status"] == "TRIAGE_HIGH_REVIEW_FIRST"
    assert confirm["schema"].endswith("triage")


def test_plan_surfaces_l3_triage_high_first(tmp_path: Path, monkeypatch):
    plan_mod = _load("post_local_pilot_qc_triage", "scripts/ops/post_local_pilot_qc.py")
    monkeypatch.setattr(plan_mod, "ROOT", tmp_path)
    out = tmp_path / "out"
    unit_dir = out / "EP11-U04" / "S01" / "cand"
    unit_dir.mkdir(parents=True)
    (unit_dir / "x.mp4").write_bytes(b"x")
    (unit_dir / "dialogue_check.json").write_text(
        json.dumps({"ok": True, "reason": "OK"}), encoding="utf-8"
    )
    (unit_dir / "l3_screen.json").write_text(
        json.dumps(
            {
                "L3_status": "SUSPECTS_OPEN",
                "triage_risk": "HIGH",
                "suspect_count": 2,
            }
        ),
        encoding="utf-8",
    )
    (unit_dir / "l3_confirm.json").write_text(
        json.dumps({"status": "TRIAGE_HIGH_REVIEW_FIRST"}), encoding="utf-8"
    )
    job = tmp_path / "jobs" / "EP11"
    (job / "assets").mkdir(parents=True)
    (job / "assets" / "prompt_source.txt").write_text("说：（ Hi. ）\n", encoding="utf-8")
    monkeypatch.setattr(plan_mod, "_JOB", {"EP11-U04": job})
    plan = plan_mod.build_plan("b", out)
    unit = next(u for u in plan["units"] if u["unit"] == "EP11-U04")
    assert unit["L3_triage"] == "HIGH"
    assert "EP11-U04" in plan["human_spot_check"]["l3_triage_high"]
    assert plan["human_spot_check"]["suggested_units"][0] == "EP11-U04"
