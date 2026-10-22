"""Deterministic sample-domain music mixing with dialogue-driven ducking."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import numpy as np

from ep_pilot_audio_qc import decode_stereo


def dialogue_envelope(frames: int, rate: int, intervals: list[tuple[float, float]]) -> np.ndarray:
    gain = np.ones(frames)
    duck = 10 ** (-9 / 20)
    for start, end in intervals:
        if not 0 <= start < end <= frames / rate:
            raise ValueError("dialogue automation interval outside timeline")
        a = max(0, round((start - 0.08) * rate))
        b, c = round(start * rate), round(end * rate)
        d = min(frames, round((end + 0.35) * rate))
        gain[a:b] = np.minimum(gain[a:b], np.linspace(1, duck, b - a, endpoint=False))
        gain[b:c] = np.minimum(gain[b:c], duck)
        gain[c:d] = np.minimum(gain[c:d], np.linspace(duck, 1, d - c, endpoint=False))
    return gain


def mix_pcm_tracks(picture: Path, tracks: list[Path], dest: Path, total: float,
                   intervals: list[tuple[float, float]], log: Path) -> None:
    voice = decode_stereo(picture)
    if len(voice) != round(total * 48000):
        raise ValueError("original voice length differs from timeline")
    bed = np.zeros_like(voice)
    for track in tracks:
        cue = decode_stereo(track)
        if cue.shape != voice.shape:
            raise ValueError("materialized music cue length mismatch")
        bed += cue
    envelope = dialogue_envelope(len(voice), 48000, intervals)
    mixed = voice + bed * envelope[:, None]
    args = ["ffmpeg", "-nostdin", "-hide_banner", "-n", "-f", "f32le",
            "-ar", "48000", "-ac", "2", "-i", "pipe:0", "-c:a", "pcm_s24le", str(dest)]
    result = subprocess.run(args, input=mixed.astype("<f4").tobytes(), capture_output=True)
    log.write_text(json.dumps(args) + "\n" + result.stderr.decode())
    if result.returncode:
        raise RuntimeError(f"PCM mix export failed; see {log}")
    automation = {"method": "sample-domain dialogue automation", "duck_db": -9,
                  "attack_s": 0.08, "release_s": 0.35, "speech_intervals": intervals,
                  "sample_frames": len(voice), "music_tracks": list(map(str, tracks))}
    log.with_suffix(".automation.json").write_text(json.dumps(automation, indent=2) + "\n")
