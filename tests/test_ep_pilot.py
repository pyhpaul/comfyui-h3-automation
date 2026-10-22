from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/episode_post"))

from ep_pilot_timeline import (  # noqa: E402
    Clip, Subtitle, Word, align_dialogue, remap_subtitles, render_srt,
    validate_clips, verify_source, wrap_caption,
)
from run_ep_post_pilot import write_subtitles  # noqa: E402


def test_rejects_empty_or_reversed_frame_interval():
    with pytest.raises(ValueError, match="interval"):
        validate_clips([Clip("U01", 24, 24)], {"U01": 100})


def test_rejects_out_of_bounds_and_overlapping_source_edits():
    with pytest.raises(ValueError, match="bounds"):
        validate_clips([Clip("U01", 0, 101)], {"U01": 100})
    with pytest.raises(ValueError, match="overlap"):
        validate_clips([Clip("U01", 0, 48), Clip("U01", 24, 72)], {"U01": 100})


def test_subtitles_remap_multiple_intervals_and_unit_offsets():
    clips = [Clip("U01", 24, 72), Clip("U01", 120, 168), Clip("U02", 0, 48)]
    cues = [Subtitle("U01", 1.2, 2.0, "First."),
            Subtitle("U01", 5.1, 6.0, "Second."),
            Subtitle("U02", 0.2, 1.0, "Third.")]
    out = remap_subtitles(cues, clips)
    assert [c.start for c in out] == pytest.approx([0.2, 2.1, 4.2])
    assert [c.end for c in out] == pytest.approx([1, 3, 5])


def test_cannot_silently_drop_or_split_scripted_dialogue():
    with pytest.raises(ValueError, match="dialogue"):
        remap_subtitles([Subtitle("U01", 1, 3, "Keep this.")], [Clip("U01", 0, 48)])


def test_ordered_alignment_keeps_first_repeat_and_handles_explicit_name_alias():
    texts = ["Damien,", "this", "isn't", "funny.", "It", "wasn't", "meant", "to", "be.",
             "It", "wasn't", "meant", "to", "be."]
    words = [Word("U03", i, i + 0.5, text) for i, text in enumerate(texts)]
    cues = align_dialogue(["Damian, this isn't funny.", "It wasn't meant to be."],
                          words, {"damien": "damian"})
    assert cues[0].text == "Damian, this isn't funny."
    assert cues[1].start == 4
    assert cues[1].end == 8.5


def test_alignment_handles_asr_split_name_via_multi_token_alias():
    # Whisper sometimes splits a name into two words ("Noah" -> "no a");
    # an alias may expand one scripted token into that token sequence.
    texts = ["I", "don't", "want", "no", "a", "caught", "in", "a", "family", "fight."]
    words = [Word("U01", i * 0.5, i * 0.5 + 0.4, text) for i, text in enumerate(texts)]
    cues = align_dialogue(["I don't want Noah caught in a family fight."],
                          words, {"noah": "no a"})
    assert cues[0].text == "I don't want Noah caught in a family fight."
    assert cues[0].start == 0
    assert cues[0].end == pytest.approx(4.9)


def test_alignment_does_not_invent_missing_words():
    with pytest.raises(ValueError, match="align"):
        align_dialogue(["You asked for the ring."], [Word("U01", 0, 1, "ring")], {})


def test_hyphenated_word_alignment_uses_actual_word_end():
    words = [Word("U04", i / 2, (i + 1) / 2, w)
             for i, w in enumerate(["You", "married", "my", "ex", "-wife?"])]
    cues = align_dialogue(["You married my ex-wife?"], words, {})
    assert cues[0].end == 2.5


def test_source_hash_mismatch_blocks_render(tmp_path):
    path = tmp_path / "source.mp4"
    path.write_bytes(b"original")
    with pytest.raises(ValueError, match="hash"):
        verify_source(path, "0" * 64)


def test_srt_rounding_and_caption_line_length():
    srt = render_srt([Subtitle("EP01", 59.9996, 61, "Hello.")])
    assert "00:01:00,000 --> 00:01:01,000" in srt
    text = "You're bringing strangers into our home?"
    lines = wrap_caption(text).splitlines()
    assert len(lines) == 2
    assert " ".join(lines) == text
    assert max(map(len, lines)) <= 36


def test_reviewed_caption_extensions_and_style_reach_both_outputs(tmp_path):
    cues = [Subtitle("EP01", 8.26, 9.16, "You don't need an audience."),
            Subtitle("EP01", 9.94, 10.94, "You asked for the ring."),
            Subtitle("EP01", 18.07, 19.63, "You're bringing strangers into our home?")]
    style = {"font_size": 38, "outline": 2,
             "end_overrides": {"You don't need an audience.": 9.65},
             "line_breaks": {"You're bringing strangers into our home?":
                             "You're bringing strangers\ninto our home?"}}
    write_subtitles(tmp_path, cues, [], style)
    srt = (tmp_path / "EP01.en.srt").read_text()
    ass = (tmp_path / "EP01.en.ass").read_text()
    assert "00:00:08,220 --> 00:00:09,650" in srt
    assert "You're bringing strangers\ninto our home?" in srt
    assert "Style: Dialogue,DejaVu Sans,38," in ass
    assert "0:00:09.65" in ass
    assert r"You're bringing strangers\Ninto our home?" in ass


def test_caption_override_cannot_cover_next_speaker(tmp_path):
    cues = [Subtitle("EP01", 1, 2, "First."), Subtitle("EP01", 3, 4, "Second.")]
    with pytest.raises(ValueError, match="overlap"):
        write_subtitles(tmp_path, cues, [], {"end_overrides": {"First.": 3.2}})


def test_caption_override_cannot_remove_spoken_words(tmp_path):
    with pytest.raises(ValueError, match="spoken"):
        write_subtitles(tmp_path, [Subtitle("EP01", 1, 2, "First.")], [],
                        {"end_overrides": {"First.": 1.5}})


def test_explicit_line_break_cannot_rewrite_dialogue(tmp_path):
    with pytest.raises(ValueError, match="text"):
        write_subtitles(tmp_path, [Subtitle("EP01", 1, 2, "First.")], [],
                        {"line_breaks": {"First.": "Different."}})
