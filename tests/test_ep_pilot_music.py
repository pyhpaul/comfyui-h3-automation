from array import array
from pathlib import Path
import shutil
import subprocess
import sys
import wave

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/episode_post"))

from ep_pilot_media import mix_music  # noqa: E402


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="requires real ffmpeg")
@pytest.mark.parametrize("repeat", range(5))
def test_nonzero_source_in_music_stays_in_planned_windows(tmp_path, repeat):
    voice = tmp_path / "voice.wav"
    with wave.open(str(voice), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(48000)
        handle.writeframes(b"\0" * 48000 * 10 * 4)
    music = tmp_path / "music.mp3"
    subprocess.run([
        "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
        "sine=frequency=733:sample_rate=48000:duration=61", "-ac", "2", str(music),
    ], check=True)
    result = tmp_path / "mix.wav"
    cues = [{"start": 2, "end": 5, "source_in": 0},
            {"start": 7, "end": 10, "source_in": 57}]
    mix_music(voice, music, cues, result, 0, 10, tmp_path / "mix.log")
    decoded = subprocess.run([
        "ffmpeg", "-nostdin", "-v", "error", "-i", str(result),
        "-ar", "48000", "-ac", "2", "-f", "f32le", "-",
    ], capture_output=True, check=True)
    samples = array("f", decoded.stdout)
    assert len(samples) == 48000 * 10 * 2
    assert max(abs(x) for x in samples[:2 * 48000 * 2]) < 1e-7, "music leaked before first cue"
    assert max(abs(x) for x in samples[5 * 48000 * 2:7 * 48000 * 2]) < 1e-7
    assert max(abs(x) for x in samples[int(7.5 * 48000) * 2:9 * 48000 * 2]) > 0.001
    assert max(abs(x) for x in samples[int(9.5 * 48000) * 2:]) > 0.001, "ending music disappeared"
