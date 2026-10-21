#!/usr/bin/env python3
"""One-shot audit for one fix-round candidate (see docs/ops/2026-10-21-chaofu-fix-retrospective-and-standard.md).

Runs everything the 2026-10-20 fix round ended up doing by hand, in one pass:
  - ASR segments vs script lines (reuses verify_chaofu_fix1.audit)
  - word-level timestamps (locate exact cut points for repeats/garble)
  - per-segment F0/RMS (female vs male voice; is a "garble" real speech?)
  - per-segment midpoint frames (frames/segN.png) for mouthing review
  - scene-cut timestamps (ffmpeg scene detection; clean cut points)
  - EP24 sky-luma night check

The verdict is NOT automated: ASR bag-of-words cannot see who is mouthing.
A human/agent still reads the frames. This tool only makes that read fast.

Usage:
  PYTHONPATH=src .venv/bin/python scripts/ops/audit_candidate.py EP33-U01 <cand_dir>
Writes <cand_dir>/candidate_audit.json and prints a summary.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location(
    "verify_chaofu", ROOT / "scripts/ops/verify_chaofu_fix1.py")
_verify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_verify)

from comfy_orch.dialogue_gate import _get_whisper_model, mp4_to_wav  # noqa: E402


def f0_rms(wav_path: Path, t0: float, t1: float) -> tuple[float, float]:
    """Median autocorrelation F0 (Hz) and RMS over [t0, t1] of a 16k mono wav."""
    import numpy as np

    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t0}", "-i", str(wav_path),
         "-t", f"{max(0.1, t1 - t0)}", "-ac", "1", "-ar", "16000",
         "-f", "s16le", "-"],
        capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    sr, win = 16000, 1024
    if len(x) < 2048:
        return 0.0, 0.0
    rms = float(np.sqrt(np.mean(x ** 2)))
    vals = []
    for i in range(0, len(x) - win, 512):
        fr = x[i:i + win] * np.hanning(win)
        ac = np.correlate(fr, fr, "full")[win - 1:]
        if ac[0] <= 0:
            continue
        lo, hi = sr // 300, sr // 60
        if hi >= len(ac):
            continue
        p = lo + int(np.argmax(ac[lo:hi]))
        if ac[p] > 0.3 * ac[0]:
            vals.append(sr / p)
    return (float(np.median(vals)) if vals else 0.0), rms


def scene_cuts(mp4: Path) -> list[float]:
    out = subprocess.run(
        ["ffmpeg", "-i", str(mp4), "-filter:v",
         "select='gt(scene,0.25)',showinfo", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    cuts = []
    for line in out.splitlines():
        if "pts_time:" in line:
            try:
                cuts.append(round(float(
                    line.split("pts_time:")[1].split()[0]), 2))
            except (ValueError, IndexError):
                pass
    return cuts


def word_timestamps(mp4: Path) -> list[dict]:
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "a.wav"
        mp4_to_wav(mp4, wav)
        model = _get_whisper_model()
        segs, _info = model.transcribe(str(wav), word_timestamps=True)
        return [{"start": round(w.start, 2), "end": round(w.end, 2),
                 "word": w.word.strip()}
                for s in segs for w in (s.words or [])]


def main() -> int:
    unit, cand_dir = sys.argv[1], Path(sys.argv[2])
    mp4s = sorted(cand_dir.glob("*.mp4"))
    if not mp4s:
        print(f"{unit} {cand_dir}: NO MP4")
        return 1
    mp4 = mp4s[-1]
    row = _verify.audit(unit, "audit", mp4, cand_dir)
    asr = row.get("asr") or {}
    segments = asr.get("segments") or []

    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "a.wav"
        mp4_to_wav(mp4, wav)
        for s in segments:
            f0, rms = f0_rms(wav, s["start"], s["end"])
            s["f0_hz"] = round(f0, 1)
            s["rms"] = round(rms, 4)

    report = {
        "unit": unit, "mp4": mp4.name,
        "asr_reason": asr.get("reason"), "overlap": asr.get("overlap"),
        "expected": asr.get("expected"),
        "segments": segments,
        "words": word_timestamps(mp4),
        "scene_cuts": scene_cuts(mp4),
        "sky_luma_top": row.get("sky_luma_top"),
    }
    (cand_dir / "candidate_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"== {unit}/{cand_dir.name} asr={report['asr_reason']} "
          f"overlap={report['overlap']} luma={report['sky_luma_top']}")
    print("  expected:", report["expected"])
    for s in segments:
        print(f"  {s['start']:5.2f}-{s['end']:5.2f}  "
              f"F0={s['f0_hz']:6.1f} RMS={s['rms']:.3f}  {s['text']}")
    print("  scene_cuts:", report["scene_cuts"])
    print("  ->", cand_dir / "candidate_audit.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
