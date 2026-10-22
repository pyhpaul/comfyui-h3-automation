from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/episode_post"))

from ep_pilot_creative import cue_fades, ending_video_filter, validate_protected_ranges
from ep_pilot_media import render_segment, mix_music, render_endcard
from ep_pilot_audio_qc import decode_stereo, check_residual_windows
from ep_pilot_timeline import Clip


def test_protected_silent_action_cannot_be_word_trimmed():
    action = [{"unit": "U04", "in_frame": 100, "out_frame": 330}]
    with pytest.raises(ValueError, match="protected action"):
        validate_protected_ranges(action, [Clip("U04", 0, 100)])
    validate_protected_ranges(action, [Clip("U04", 0, 330)])


@pytest.mark.parametrize("effect", [
    {"start_frame": 10, "end_frame": 100, "zoom": 1.035},
    {"start_frame": 10, "end_frame": 80, "zoom": 1.5},
    {"start_frame": -1, "end_frame": 80, "zoom": 1.03},
    {"start_frame": 10, "end_frame": 80, "zoom": 1.101},
])
def test_rejects_unsafe_push(effect):
    with pytest.raises(ValueError, match="ending push"):
        ending_video_filter(effect, 100)


def test_cue_config_rejects_invalid_fade_and_source():
    with pytest.raises(ValueError, match="fade"):
        cue_fades({"start": 1, "end": 2, "source_in": 0, "fade_in": 3}, 4)
    with pytest.raises(ValueError, match="cue"):
        cue_fades({"start": 1, "end": 2, "source_in": -1}, 4)


def test_visible_push_is_accepted_but_remains_bounded():
    value = ending_video_filter({"start_frame": 276, "end_frame": 324,
                                 "zoom": 1.10, "anchor_x": 0.6, "anchor_y": 0.42}, 330)
    assert "0.10000000" in value
    assert "on-276" in value


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="requires real ffmpeg")
def test_clean_card_removes_credit_pixels_but_keeps_title(tmp_path):
    variations = []
    for enabled in (True, False):
        path = tmp_path / f"card-{enabled}.mkv"
        render_endcard(path, 12, tmp_path / f"card-{enabled}.log", enabled)
        result = subprocess.run(["ffmpeg", "-v", "error", "-ss", "0.3", "-i", str(path),
                                 "-frames:v", "1", "-pix_fmt", "gray", "-f", "rawvideo", "-"],
                                capture_output=True, check=True)
        variations.append(np.frombuffer(result.stdout, dtype=np.uint8).reshape(1376, 768))
    credited, clean = variations
    assert np.ptp(credited[1140:1220]) > 50
    assert np.ptp(clean[1140:1220]) <= 2
    assert np.ptp(clean[650:720]) > 50


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="requires real ffmpeg")
def test_real_push_preserves_frames_and_changes_only_planned_picture(tmp_path):
    source = tmp_path / "source.mkv"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "testsrc2=s=768x1376:r=24:d=1", "-f", "lavfi", "-i",
                    "anullsrc=r=48000:cl=stereo:d=1", "-c:v", "libx264",
                    "-preset", "ultrafast", "-c:a", "pcm_s24le", str(source)], check=True)
    plain, pushed = tmp_path / "plain.mkv", tmp_path / "push.mkv"
    render_segment(source, plain, 0, 24, 0, True, tmp_path / "plain.log")
    render_segment(source, pushed, 0, 24, 0, True, tmp_path / "push.log",
                   {"start_frame": 8, "end_frame": 16, "zoom": 1.04})
    def pixels(path):
        result = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path),
                                 "-pix_fmt", "gray", "-f", "rawvideo", "-"],
                                capture_output=True, check=True)
        return np.frombuffer(result.stdout, dtype=np.uint8).reshape(-1, 1376, 768).astype(float)
    a, b = pixels(plain), pixels(pushed)
    assert a.shape == b.shape == (24, 1376, 768)
    assert np.abs(a[15] - b[15]).mean() > np.abs(a[0] - b[0]).mean() + 1
    assert np.array_equal(decode_stereo(plain), decode_stereo(pushed))


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="requires real ffmpeg")
def test_distinct_cue_sources_levels_and_fades_are_rendered(tmp_path):
    sources = []
    for name, hz in (("low", 300), ("high", 900), ("voice", 0)):
        path = tmp_path / f"{name}.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                        f"sine=frequency={hz}:sample_rate=48000:duration=6",
                        "-ac", "2", str(path)], check=True)
        sources.append(path)
    low, high, voice = sources
    cues = [{"start": 1, "end": 2, "source_in": 1, "fade_in": 0.1, "fade_out": 0.1},
            {"start": 4, "end": 5, "source_in": 0, "path": str(high),
             "gain_offset_db": -6, "fade_in": 0.1, "fade_out": 0.1}]
    target = tmp_path / "mix.wav"
    mix_music(voice, low, cues, target, 0, 6, tmp_path / "mix.log")
    samples = decode_stereo(target)
    check_residual_windows(samples, 48000, cues, 6)
    chunks = [samples[int(t * 48000):int((t + 0.5) * 48000), 0] for t in (1.2, 4.2)]
    peaks = [np.argmax(np.abs(np.fft.rfft(x))) * 48000 / len(x) for x in chunks]
    assert peaks == pytest.approx([300, 900], abs=2)
    assert np.sqrt(np.mean(chunks[1] ** 2) / np.mean(chunks[0] ** 2)) == pytest.approx(10 ** (-6 / 20), abs=0.01)
