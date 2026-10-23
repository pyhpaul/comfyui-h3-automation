from pathlib import Path
import shutil
import subprocess
import sys
import json

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/episode_post"))

from episode_ending import ending_layout, bloom_filter, render_bloom_segment, render_sfx
from ep_pilot_audio_qc import decode_stereo, check_residual_windows
from ep_pilot_timeline import Clip
from ep_pilot_media import concatenate


def preset():
    return json.loads((ROOT / "docs/ending-presets/bloom-hold-suspense-v1.json").read_text())


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="requires real ffmpeg")
def test_concat_preserves_exact_sample_count_across_fractional_milliseconds(tmp_path):
    paths = []
    for i, frames in enumerate((4, 8, 6)):
        path = tmp_path / f"part-{i}.mkv"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                        f"color=s=64x64:r=24:d={frames / 24}", "-f", "lavfi", "-i",
                        f"anullsrc=r=48000:cl=stereo:d={frames / 24}",
                        "-c:v", "libx264", "-c:a", "pcm_s24le", str(path)], check=True)
        paths.append(path)
    result = tmp_path / "joined.mkv"
    concatenate(paths, result, tmp_path / "concat.log", 18)
    assert len(decode_stereo(result)) == 36000
    with pytest.raises(ValueError, match="source PCM lengths"):
        concatenate(paths, tmp_path / "bad.mkv", tmp_path / "bad.log", 19)


def test_layout_maps_relative_preset_to_full_episode():
    layout = ending_layout(1236, preset())
    assert layout["total_frames"] == 1290
    assert layout["bloom_start_s"] == pytest.approx(50.25)
    assert layout["hold_start_s"] == 51.5
    assert layout["card_start_s"] == 52.5


def test_layout_tail_pad_shifts_ending_without_changing_story():
    base = ending_layout(1236, preset())
    padded = ending_layout(1236, preset(), tail_pad_frames=24)
    assert padded["story_frames"] == 1236
    assert padded["tail_pad_frames"] == 24
    assert padded["total_frames"] == base["total_frames"] + 24
    assert padded["bloom_start_s"] == pytest.approx(base["bloom_start_s"] + 1.0)
    assert padded["hold_start_s"] == pytest.approx(base["hold_start_s"] + 1.0)
    with pytest.raises(ValueError, match="tail_pad_frames"):
        ending_layout(1236, preset(), tail_pad_frames=-1)


def test_rejects_unapproved_preset_version():
    data = preset()
    data["version"] = 999
    with pytest.raises(ValueError, match="unsupported"):
        ending_layout(1236, data)


def test_rejects_clip_too_short_for_approved_effect():
    with pytest.raises(ValueError, match="short"):
        bloom_filter(50, preset())


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="requires real ffmpeg")
def test_bloom_segment_really_adds_hold_and_silence(tmp_path):
    source, result = tmp_path / "source.mkv", tmp_path / "bloom.mkv"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "testsrc2=s=768x1376:r=24:d=4", "-f", "lavfi", "-i",
                    "sine=frequency=440:sample_rate=48000:duration=4", "-ac", "2",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "pcm_s24le", str(source)], check=True)
    render_bloom_segment(source, result, Clip("U04", 0, 96), 0, preset(), tmp_path / "render.log")
    data = subprocess.run(["ffmpeg", "-v", "error", "-i", str(result),
                           "-pix_fmt", "gray", "-f", "rawvideo", "-"], capture_output=True, check=True)
    frames = np.frombuffer(data.stdout, dtype=np.uint8).reshape(-1, 1376, 768)
    assert len(frames) == 120
    assert np.abs(frames[95].astype(float) - frames[110]).mean() < 1
    audio = decode_stereo(result)
    assert len(audio) == 5 * 48000
    assert np.max(np.abs(audio[4 * 48000:])) == 0


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="requires real ffmpeg")
def test_bloom_segment_tail_pad_freezes_last_frame_silently(tmp_path):
    source, result = tmp_path / "source.mkv", tmp_path / "bloom.mkv"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "testsrc2=s=768x1376:r=24:d=4", "-f", "lavfi", "-i",
                    "sine=frequency=440:sample_rate=48000:duration=4", "-ac", "2",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "pcm_s24le", str(source)], check=True)
    render_bloom_segment(source, result, Clip("U04", 0, 96), 0, preset(),
                         tmp_path / "render.log", tail_pad_frames=24)
    data = subprocess.run(["ffmpeg", "-v", "error", "-i", str(result),
                           "-pix_fmt", "gray", "-f", "rawvideo", "-"], capture_output=True, check=True)
    frames = np.frombuffer(data.stdout, dtype=np.uint8).reshape(-1, 1376, 768)
    assert len(frames) == 144
    # padded clones (96..119) are one frozen frame; once the bloom weight is
    # fully ramped they must be identical to each other
    assert np.abs(frames[110].astype(float) - frames[119]).mean() < 1
    audio = decode_stereo(result)
    assert len(audio) == 6 * 48000
    assert np.max(np.abs(audio[4 * 48000:])) == 0


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="requires real ffmpeg")
def test_sfx_materialization_uses_shifted_sample_timeline(tmp_path):
    (tmp_path / "work").mkdir()
    paths, cues = render_sfx(preset(), ending_layout(96, preset()), tmp_path, -2)
    assert cues[0]["start"] == pytest.approx(2.7)
    assert cues[1]["start"] == 4
    for path, cue in zip(paths, cues):
        samples = decode_stereo(path)
        assert len(samples) == 300000
        assert check_residual_windows(samples, 48000, [cue], 6.25)["passed"]
