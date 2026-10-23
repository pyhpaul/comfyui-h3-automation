"""Verify actual music presence and absence on the sample timeline."""
from __future__ import annotations

from pathlib import Path
import subprocess

import numpy as np


def check_residual_windows(residual: np.ndarray, rate: int, cues: list[dict], total: float) -> dict:
    if len(residual) != round(total * rate):
        raise ValueError("music residual sample length differs from timeline")
    allowed = np.zeros(len(residual), dtype=bool)
    windows = []
    for cue in cues:
        start, end = float(cue["start"]), float(cue["end"])
        if not 0 <= start < end <= total:
            raise ValueError("invalid music cue bounds")
        first, last = round(start * rate), round(end * rate)
        allowed[first:last] = True
        section = residual[first:last]
        rms = float(np.sqrt(np.mean(section ** 2)))
        if rms < 1e-6:
            raise ValueError(f"missing scheduled music at {start}-{end}")
        windows.append({"start": start, "end": end, "residual_rms": rms})
    outside = float(np.max(np.abs(residual[~allowed]))) if np.any(~allowed) else 0.0
    if outside > 1e-7:
        raise ValueError(f"music outside scheduled windows: peak={outside}")
    tail = residual[max(0, len(residual) - rate):]
    tail_rms = float(np.sqrt(np.mean(tail ** 2)))
    if any(abs(cue["end"] - total) < 1e-6 for cue in cues) and tail_rms < 1e-6:
        raise ValueError("missing ending music")
    return {"passed": True, "sample_rate": rate, "sample_frames": len(residual),
            "outside_cue_peak": outside, "scheduled_windows": windows,
            "tail_music_rms": tail_rms,
            "scope": "pre-normalization music residual, not subjective listening"}


def decode_stereo(path: Path, rate: int = 48000) -> np.ndarray:
    result = subprocess.run([
        "ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
        "-vn", "-ar", str(rate), "-ac", "2", "-f", "f32le", "-",
    ], capture_output=True, check=True)
    return np.frombuffer(result.stdout, dtype="<f4").astype(np.float64).reshape(-1, 2)


def check_music_timing(picture: Path, mix: Path, cues: list[dict], total: float) -> dict:
    voice, mixed = decode_stereo(picture), decode_stereo(mix)
    if voice.shape != mixed.shape:
        raise ValueError("voice and music mix sample length mismatch")
    return check_residual_windows(mixed - voice, 48000, cues, total)
