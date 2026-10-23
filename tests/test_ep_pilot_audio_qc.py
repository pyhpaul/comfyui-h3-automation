from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/episode_post"))
from ep_pilot_audio_qc import check_residual_windows  # noqa: E402
from ep_pilot_mix import dialogue_envelope  # noqa: E402


CUES = [{"start": 2, "end": 5}, {"start": 7, "end": 10}]


def residual():
    samples = np.zeros((1000, 2))
    samples[200:500] = 0.01
    samples[700:1000] = 0.01
    return samples


def test_music_qc_accepts_exact_windows_and_tail():
    result = check_residual_windows(residual(), 100, CUES, 10)
    assert result["passed"] is True
    assert result["outside_cue_peak"] == 0
    assert result["tail_music_rms"] > 0


def test_music_qc_rejects_unplanned_intro_music():
    samples = residual()
    samples[:100] = 0.02
    with pytest.raises(ValueError, match="outside"):
        check_residual_windows(samples, 100, CUES, 10)


def test_music_qc_rejects_missing_ending_cue():
    samples = residual()
    samples[700:] = 0
    with pytest.raises(ValueError, match="missing"):
        check_residual_windows(samples, 100, CUES, 10)


def test_music_qc_rejects_sample_length_mismatch():
    with pytest.raises(ValueError, match="length"):
        check_residual_windows(residual()[:-1], 100, CUES, 10)


def test_dialogue_duck_has_smooth_attack_hold_and_release():
    envelope = dialogue_envelope(500, 100, [(2, 3)])
    assert envelope[180] == 1
    assert envelope[250] == pytest.approx(10 ** (-9 / 20))
    assert envelope[340] == 1
    assert np.max(np.abs(np.diff(envelope))) < 0.1


def test_overlapping_dialogue_ducks_do_not_rebound_between_lines():
    envelope = dialogue_envelope(500, 100, [(2, 3), (2.8, 4)])
    assert np.max(envelope[200:400]) == pytest.approx(10 ** (-9 / 20))
