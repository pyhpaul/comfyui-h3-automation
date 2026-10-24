"""Pre-queue render-risk patterns from lihun failall classes."""
from __future__ import annotations

from comfy_orch.pack_render_risk import (
    estimate_dialogue_duration_s,
    high_risk_codes,
    scan_render_risks,
)


def test_silent_unit_open_mouth_is_high_b():
    prompt = "镜头：两人同框。角色开口说话，口型同步。无旁白。"
    risks = scan_render_risks(prompt)
    assert "B" in high_risk_codes(risks)


def test_two_shot_dialogue_without_listener_lock_is_high_e():
    prompt = (
        "双人同框，另一人在纵深。"
        "（Hello.）"
        "说话者口型同步开口。"
    )
    risks = scan_render_risks(prompt)
    assert "E" in high_risk_codes(risks)


def test_listener_closed_clears_e():
    prompt = (
        "双人同框，另一人在纵深。"
        "（Hello.）"
        "说话者开口；听者全程闭口无声，禁止同念。"
    )
    risks = scan_render_risks(prompt)
    assert "E" not in high_risk_codes(risks)


def test_short_question_med_c():
    prompt = "（Whose?） Then what."
    risks = scan_render_risks(prompt)
    assert any(r.code == "C" for r in risks)


def test_duration_slack_med():
    prompt = "（Hi.）"
    risks = scan_render_risks(prompt, default_duration_s=14.0)
    assert any(r.code == "DURATION" for r in risks)
    assert estimate_dialogue_duration_s(prompt) < 10.0
