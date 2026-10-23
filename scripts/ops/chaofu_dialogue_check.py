#!/usr/bin/env python3
"""Dialogue check for pulled Chaofu problem units.

For each unit: ASR the pulled mp4, score against （） lines in the job's
prompt_source.txt, dump transcript segments with timestamps, and extract
sample frames (first-shot area + segment midpoints) for lip-attribution
review. Writes a JSON report + frames under the check dir.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from comfy_orch.dialogue_gate import (  # noqa: E402
    extract_expected_dialogue,
    mp4_to_wav,
    score_transcript,
    transcribe_wav_faster_whisper,
)

_ASSET_CODE = re.compile(r"（(?:W-|CREATURE-|scene-|char-|prop-)[^）]*）")

UNITS = [
    "EP06-U04", "EP23-U01", "EP23-U05", "EP33-U01", "EP41-U05",
    "EP42-U02", "EP42-U04", "EP43-U05", "EP50-U02", "EP51-U06",
    "EP53-U05",
]


def job_dir(unit: str) -> Path:
    ep, uu = unit.split("-")
    matches = sorted((ROOT / "jobs/ep_units").glob(f"{ep}-潮缚-v1-{uu}"))
    if not matches:
        raise SystemExit(f"job not found for {unit}")
    return matches[0]


def grab_frame(mp4: Path, t: float, out: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}",
         "-i", str(mp4), "-frames:v", "1", "-vf", "scale=360:-1", str(out)],
        check=True,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-dir", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    report = {}
    for unit in UNITS:
        mp4s = sorted((args.check_dir / unit).glob("*-audio.mp4"))
        if not mp4s:
            print(f"{unit}: NO MP4")
            continue
        mp4 = mp4s[-1]
        jd = job_dir(unit)
        prompt_text = (jd / "assets/prompt_source.txt").read_text()
        cleaned = _ASSET_CODE.sub("", prompt_text)
        expected = extract_expected_dialogue(cleaned)

        with tempfile.TemporaryDirectory() as td:
            wav = Path(td) / "audio.wav"
            mp4_to_wav(mp4, wav)
            heard, segments = transcribe_wav_faster_whisper(wav)
        verdict = score_transcript(
            heard=heard, segments=segments, expected=expected)

        frames_dir = args.check_dir / unit / "frames"
        frames_dir.mkdir(exist_ok=True)
        # first-shot frames (QC flagged first segment on EP06-U04 / EP53-U05)
        for label, t in [("t01", 1.0), ("t03", 3.0), ("t05", 5.0)]:
            grab_frame(mp4, t, frames_dir / f"{label}.png")
        for i, (a, b, _t) in enumerate(segments):
            mid = (float(a) + float(b)) / 2.0
            grab_frame(mp4, mid, frames_dir / f"seg{i}_{mid:.1f}s.png")

        report[unit] = {
            "mp4": mp4.name,
            "expected": expected.lines,
            "segments": [
                {"start": a, "end": b, "text": t} for a, b, t in segments
            ],
            "transcript": heard,
            "verdict": {
                "ok": verdict.ok, "reason": verdict.reason,
                "overlap": verdict.overlap,
                "missing": verdict.missing, "extras": verdict.extras,
            },
        }
        print(f"{unit}: {verdict.reason} overlap={verdict.overlap} "
              f"missing={verdict.missing} extras={verdict.extras} "
              f"heard={heard[:100]!r}")
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print("report ->", args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
