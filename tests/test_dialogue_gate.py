"""Dialogue gate: expected lines from prompt_source + transcript scoring."""
from __future__ import annotations

from pathlib import Path

from comfy_orch.dialogue_gate import (
    DialogueVerdict,
    extract_expected_dialogue,
    gate_enabled,
    score_transcript,
    select_primary_mp4,
)


def test_extract_spoken_lines_from_fullwidth_parens():
    src = (
        "旁白忽略\n"
        "人物对白只能读（）内的英文，禁止读旁白。\n"
        "说：（ Harlow's boss knows you well. I wonder if he'll still deal with you later. ）\n"
        "再说：（ Three years on your own. Ever find anything over a hundred thousand? ）\n"
    )
    exp = extract_expected_dialogue(src)
    assert exp.silent is False
    assert exp.lines == [
        "Harlow's boss knows you well. I wonder if he'll still deal with you later.",
        "Three years on your own. Ever find anything over a hundred thousand?",
    ]


def test_extract_marks_silent_unit():
    src = "人物对白只能读（）内的英文，禁止读旁白。本条没有任何对白。所有角色全程闭口。\n"
    exp = extract_expected_dialogue(src)
    assert exp.silent is True
    assert exp.lines == []


def test_score_ok_when_heard_matches():
    expected = extract_expected_dialogue(
        "说：（ Wade cut my safety line. ） 说：（ He did what? ）"
    )
    verdict = score_transcript(
        heard="Wade cut my safety line. He did what?",
        segments=[(0.5, 3.0, "Wade cut my safety line."), (3.5, 5.0, "He did what?")],
        expected=expected,
    )
    assert verdict.ok is True
    assert verdict.reason == "OK"
    assert verdict.extras == []


def test_score_fails_on_tail_garbage_glued_to_good_line():
    expected = extract_expected_dialogue(
        "说：（ It's not just the money. ）"
    )
    verdict = score_transcript(
        heard="It's not just the money. It's only common just to the right of Roger Tardy",
        segments=[
            (
                9.0,
                13.9,
                "It's not just the money. It's only common just to the right of Roger Tardy",
            )
        ],
        expected=expected,
    )
    assert verdict.ok is False
    assert verdict.reason == "BAD_extra"
    assert any("Roger" in e or "roger" in e.lower() for e in verdict.extras)


def test_score_ok_when_all_lines_in_one_asr_segment():
    """Whisper often merges several short lines; that is not ad-lib."""
    expected = extract_expected_dialogue(
        "说：（ Then we don't want that money. ） "
        "说：（ Mom, your treatment isn't done. ） "
        "说：（ Then we skip the treatment. ）"
    )
    heard = "Then we don't want that money mom your treatment isn't done then we skip the treatment"
    verdict = score_transcript(
        heard=heard,
        segments=[(0.5, 12.0, heard)],
        expected=expected,
    )
    assert verdict.ok is True
    assert verdict.reason == "OK"
    assert verdict.extras == []


def test_score_silent_fails_on_any_speech():
    expected = extract_expected_dialogue("本条没有任何对白。禁止口型说话。\n")
    verdict = score_transcript(
        heard="Hello there",
        segments=[(1.0, 2.0, "Hello there")],
        expected=expected,
    )
    assert verdict.ok is False
    assert verdict.reason == "BAD_speech_on_silent"


def test_score_accepts_number_form_variants():
    expected = extract_expected_dialogue(
        "说：（ Thirty-eight thousand isn't three hundred bucks. ）"
    )
    verdict = score_transcript(
        heard="$38,000 isn't 300 bucks.",
        segments=[(0.5, 3.0, "$38,000 isn't 300 bucks.")],
        expected=expected,
    )
    assert verdict.ok is True
    assert verdict.reason == "OK"


def test_score_accepts_seven_hundred_thousand_as_digits():
    expected = extract_expected_dialogue(
        "说：（ Cole, that's seven hundred thousand. Not seven hundred bucks. Keep it. ）"
    )
    verdict = score_transcript(
        heard="Cole, that's $700,000, not $700 bucks. Keep it.",
        segments=[
            (0.0, 5.0, "Cole, that's $700,000, not $700 bucks."),
            (5.0, 6.0, "Keep it."),
        ],
        expected=expected,
    )
    assert verdict.ok is True
    assert verdict.reason == "OK"


def test_dialogue_verdict_dataclass_fields():
    v = DialogueVerdict(ok=True, reason="OK", extras=[], missing=[], overlap=1.0)
    assert v.ok and v.reason == "OK"


def test_select_primary_mp4_prefers_pass1_audio(tmp_path: Path):
    a = tmp_path / "clip-pass2.mp4"
    b = tmp_path / "clip-pass1_00001-audio.mp4"
    a.write_bytes(b"x")
    b.write_bytes(b"y")
    assert select_primary_mp4([a, b]) == b


def test_gate_enabled_from_env_and_flag():
    assert gate_enabled(True, env="") is True
    assert gate_enabled(False, env="1") is False
    assert gate_enabled(None, env="1") is True
    assert gate_enabled(None, env="0") is False
    assert gate_enabled(None, env="") is False


def test_bump_noise_seed_changes_random_noise_for_retry():
    from comfy_orch.dialogue_gate import bump_noise_seed

    workflow = {
        "256": {"class_type": "RandomNoise", "inputs": {"noise_seed": 1012014866441350}},
        "99": {"class_type": "KSampler", "inputs": {"seed": 1}},
    }
    out = bump_noise_seed(workflow, attempt=2)
    assert out["256"]["inputs"]["noise_seed"] != 1012014866441350
    assert out["99"]["inputs"]["seed"] != 1
    # attempt 1 keeps base
    same = bump_noise_seed(workflow, attempt=1)
    assert same["256"]["inputs"]["noise_seed"] == 1012014866441350
    assert same["99"]["inputs"]["seed"] == 1


def test_score_accepts_fifty_thousand_digit_asr():
    expected = extract_expected_dialogue("说：（ Fifty thousand. ）")
    verdict = score_transcript(
        heard="50,000.",
        segments=[(9.0, 10.0, "50,000.")],
        expected=expected,
    )
    assert verdict.ok is True
    assert verdict.reason == "OK"


def test_extract_dedupes_repeated_fullwidth_lines():
    text = (
        "1. （ Ms. Harlow? ）\n"
        "再说：（ Ms. Harlow? ）\n"
        "又说：（ Hello. ）\n"
    )
    expected = extract_expected_dialogue(text)
    assert expected.lines == ["Ms. Harlow?", "Hello."]


def test_score_ok_ignores_trailing_asr_hallucination_after_full_cover():
    """Silent Chinese mouths after a clean line → Whisper gibberish segments; not ad-lib."""
    expected = extract_expected_dialogue(
        "说：（ Cole, that's $700,000. Not $700 bucks. Your mom's treatment still needs money. Keep it. ）"
    )
    verdict = score_transcript(
        heard=(
            "Cole, that's $700,000. Not $700 bucks. Your mom's treatment still needs money. Keep it. "
            "Sinharlo Yosiyo reckoned to trying to Trenect. You earned several li's"
        ),
        segments=[
            (1.0, 8.0, "Cole, that's $700,000. Not $700 bucks. Your mom's treatment still needs money. Keep it."),
            (8.5, 11.0, "Sinharlo Yosiyo reckoned to trying to Trenect."),
            (11.2, 12.5, "You earned several li's"),
        ],
        expected=expected,
    )
    assert verdict.ok is True
    assert verdict.reason == "OK"
    assert verdict.extras == []
