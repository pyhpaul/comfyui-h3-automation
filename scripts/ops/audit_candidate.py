#!/usr/bin/env python3
"""Automated screening for one fix-round candidate.

This tool gathers evidence; it does not audit speaker attribution and it
never issues a verdict. It produces:

  - ASR segments vs script lines (reuses verify_chaofu_fix1.audit)
  - word-level timestamps (locate exact cut points for repeats/garble)
  - per-segment F0/RMS (female vs male voice; is a "garble" real speech?)
  - dense frames across every dialogue segment (screening aids only)
  - scene-cut timestamps (ffmpeg scene detection; clean cut points)
  - EP24 sky-luma night check
  - human_review.json: an initially UNREVIEWED full-watch checklist

Why the hard split: on 2026-10-21, ASR plus sparse midpoint frames produced
false STRICT verdicts for EP01-U06-seed2 and EP02-U04-indep; complete human
watching rejected both. A strict/relaxed verdict may only be recorded in
fix_registry.py with method=full-dialogue-watch and named review evidence.

Usage:
  PYTHONPATH=src .venv/bin/python scripts/ops/audit_candidate.py EP33-U01 <cand_dir>
Writes <cand_dir>/candidate_audit.json and <cand_dir>/human_review.json.
"""
from __future__ import annotations

import argparse
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

from comfy_orch.dialogue_gate import (  # noqa: E402
    _get_whisper_model, extract_expected_dialogue, mp4_to_wav,
)


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


def review_frame_times(start: float, end: float, step: float = 0.25) -> list[float]:
    """Frame times spanning a whole dialogue segment, endpoints included.

    These frames are navigation aids for a human reviewer. They are not,
    by themselves, evidence that the correct person mouthed a line.
    """
    if step <= 0:
        raise ValueError("step must be positive")
    start, end = float(start), float(end)
    if end < start:
        start, end = end, start
    times: list[float] = []
    t = start
    while t < end:
        times.append(round(t, 2))
        t += step
    if not times or times[-1] != round(end, 2):
        times.append(round(end, 2))
    return times


def build_human_review(
    unit: str,
    mp4_name: str,
    segments: list[dict],
    expected_lines: list[str] | None = None,
) -> dict:
    """Create the mandatory, initially incomplete, full-watch checklist."""
    expected_lines = expected_lines or []
    count = max(len(segments), len(expected_lines))
    lines = []
    for i in range(count):
        seg = segments[i] if i < len(segments) else {}
        lines.append({
            "index": i + 1,
            "status": "UNREVIEWED",
            "segment_start": seg.get("start"),
            "segment_end": seg.get("end"),
            "heard_text": seg.get("text", ""),
            "expected_text": expected_lines[i] if i < len(expected_lines) else "",
            "checks": {
                "expected_speaker": "UNREVIEWED",
                "mouth_owner": "UNREVIEWED",
                "other_visible_mouths": "UNREVIEWED",
                "line_complete": "UNREVIEWED",
                "line_order": "UNREVIEWED",
            },
            "reviewer_note": "",
        })
    return {
        "unit": unit,
        "mp4": mp4_name,
        "status": "REQUIRED_NOT_DONE",
        "may_issue_verdict": False,
        "method_required": "full-dialogue-watch",
        "automated_evidence_is_screening_only": True,
        "instructions": [
            "Watch every dialogue segment in motion, with audio, from at "
            "least 0.5s before its first word through 0.5s after its last.",
            "For each scripted line record who actually mouths it, whether "
            "every other visible mouth stays closed, and whether the line "
            "is complete and in order.",
            "Dense still frames may locate moments to inspect; they cannot "
            "replace watching the segment and cannot support a verdict.",
            "Only after every line is checked may fix_registry.py record "
            "strict/relaxed, with reviewer and evidence named.",
        ],
        "reviewer": "",
        "reviewed_at": "",
        "lines": lines,
    }


def group_word_segments(words: list[dict], silence_gap: float = 0.65) -> list[dict]:
    """Group word timestamps into reviewable utterances on silence gaps."""
    segments: list[dict] = []
    current: dict | None = None
    for word in words:
        start, end, text = word["start"], word["end"], word["word"]
        if current is None or start - current["end"] > silence_gap:
            current = {"start": start, "end": end, "text": text}
            segments.append(current)
        else:
            current["end"] = end
            current["text"] = f"{current['text']} {text}".strip()
    return segments


def load_expected_lines(prompt_source: Path) -> list[str]:
    source = _verify._ASSET_CODE.sub(
        "", prompt_source.read_text(encoding="utf-8"))
    return extract_expected_dialogue(source).lines


def extract_review_frames(mp4: Path, cand_dir: Path, segments: list[dict]) -> None:
    """Extract dense stills as navigation aids (never as a verdict)."""
    frames_root = cand_dir / "frames"
    for i, seg in enumerate(segments):
        out_dir = frames_root / f"review_seg{i + 1}"
        out_dir.mkdir(parents=True, exist_ok=True)
        for j, t in enumerate(review_frame_times(seg["start"], seg["end"])):
            _verify.grab(mp4, t, out_dir / f"f{j:02d}_t{t:.2f}.png")


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
    ap = argparse.ArgumentParser()
    ap.add_argument("unit")
    ap.add_argument("cand_dir", type=Path)
    ap.add_argument("--prompt-source", type=Path, default=None,
                    help="prompt_source.txt for units outside the legacy "
                         "verify_chaofu_fix1 dialogue whitelist")
    args = ap.parse_args()
    unit, cand_dir = args.unit, args.cand_dir
    mp4s = sorted(cand_dir.glob("*.mp4"))
    if not mp4s:
        print(f"{unit} {cand_dir}: NO MP4")
        return 1
    mp4 = mp4s[-1]
    row = _verify.audit(unit, "audit", mp4, cand_dir)
    asr = row.get("asr") or {}
    segments = asr.get("segments") or []

    words = word_timestamps(mp4)
    review_segments = segments or group_word_segments(words)
    expected_lines = asr.get("expected") or []
    if args.prompt_source:
        expected_lines = load_expected_lines(args.prompt_source)

    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "a.wav"
        mp4_to_wav(mp4, wav)
        for s in review_segments:
            f0, rms = f0_rms(wav, s["start"], s["end"])
            s["f0_hz"] = round(f0, 1)
            s["rms"] = round(rms, 4)

    extract_review_frames(mp4, cand_dir, review_segments)
    review_path = cand_dir / "human_review.json"
    if review_path.exists():
        # Never erase a review already in progress or completed.
        review = json.loads(review_path.read_text(encoding="utf-8"))
    else:
        review = build_human_review(
            unit, mp4.name, review_segments, expected_lines)
        review_path.write_text(
            json.dumps(review, ensure_ascii=False, indent=1), encoding="utf-8")

    report = {
        "unit": unit, "mp4": mp4.name,
        "decision": "NOT_DECIDED",
        "automated_checks_only": True,
        "review_status": review.get("status", "REQUIRED_NOT_DONE"),
        "human_review_file": review_path.name,
        "asr_reason": asr.get("reason"), "overlap": asr.get("overlap"),
        "expected": expected_lines,
        "segments": segments,
        "review_segments": review_segments,
        "words": words,
        "scene_cuts": scene_cuts(mp4),
        "sky_luma_top": row.get("sky_luma_top"),
    }
    (cand_dir / "candidate_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"== {unit}/{cand_dir.name} asr={report['asr_reason']} "
          f"overlap={report['overlap']} luma={report['sky_luma_top']}")
    print("  expected:", report["expected"])
    for s in review_segments:
        print(f"  {s['start']:5.2f}-{s['end']:5.2f}  "
              f"F0={s['f0_hz']:6.1f} RMS={s['rms']:.3f}  {s['text']}")
    print("  scene_cuts:", report["scene_cuts"])
    print("  DECISION=NOT_DECIDED "
          f"review_status={report['review_status']} "
          "(automated screening only; full dialogue watch required)")
    print("  ->", cand_dir / "candidate_audit.json")
    print("  ->", review_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
