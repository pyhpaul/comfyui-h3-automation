#!/usr/bin/env python3
"""Batch dialogue audit for already-rendered mp4s.

For each mp4, extract the audio track (ffmpeg -> 16k mono wav), ASR it with
faster-whisper, and score the transcript against the English lines inside
fullwidth （） in the matching prompt_source.txt (comfy_orch.dialogue_gate).
Prints one line per unit and writes a JSON report. Only FAIL rows need a
human to open the video.

Usage:
  PYTHONPATH=src python scripts/ops/batch_dialogue_check.py \
    --pairs wuxi_orig:jobs/ep_units_wenwu_test \
    --video-root jobs/wenwu_ab_test/wuxi_orig \
    --report runs/dialogue_check_wuxi_orig.json

--pairs maps a video filename stem prefix (EP17-U01) to its job dir via
<jobs-root>/<episode-dir-prefix>-<unit>; simpler: --job-map EP=prefix.
"""
from __future__ import annotations

import argparse
import json
import re
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

# Asset codes in 参考设定 look like dialogue to the extractor:
# Liam @char-001（W-LIAM-04）— strip them before scoring.
_ASSET_CODE = re.compile(r"（(?:W-|CREATURE-|scene-|char-|prop-)[^）]*）")


def _ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video-root", type=Path, required=True,
                    help="dir containing <EP>/<EP>-<U>.mp4 (or flat *.mp4)")
    ap.add_argument("--job-root", type=Path, required=True,
                    help="dir containing job dirs named <prefix>-<unit>")
    ap.add_argument("--prefix", action="append", required=True,
                    help="EP17=EP17-兽王降临-wenwu (repeatable)")
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--emit-srt", action="store_true",
                    help="also write <video>.srt (UTF-8) beside each mp4 for 剪映 import")
    ap.add_argument("--zh-map", type=Path, default=None,
                    help="optional JSON {english line: chinese} — matched lines "
                         "get a Chinese second row in the SRT")
    args = ap.parse_args()
    zh_map: dict[str, str] = {}
    if args.zh_map:
        zh_map = json.loads(args.zh_map.read_text(encoding="utf-8"))

    prefixes = dict(p.split("=", 1) for p in args.prefix)
    rows = []
    mp4s = sorted(args.video_root.rglob("*.mp4"))
    for mp4 in mp4s:
        stem = mp4.stem  # EP17-U01
        ep, unit = stem.rsplit("-", 1)
        prefix = prefixes.get(ep)
        if not prefix:
            print(f"SKIP {stem}: no prefix for {ep}")
            continue
        job = args.job_root / f"{prefix}-{unit}"
        source_path = job / "assets" / "prompt_source.txt"
        if not source_path.is_file():
            print(f"SKIP {stem}: missing {source_path}")
            continue
        source = _ASSET_CODE.sub("", source_path.read_text(encoding="utf-8"))
        expected = extract_expected_dialogue(source)
        with tempfile.TemporaryDirectory(prefix="h3-dlg-") as tmp:
            wav = Path(tmp) / "audio.wav"
            mp4_to_wav(mp4, wav)
            heard, segments = transcribe_wav_faster_whisper(wav)
        verdict = score_transcript(heard=heard, segments=segments, expected=expected)
        row = {
            "video": str(mp4), "episode": ep, "unit": unit,
            "expected_lines": expected.lines, "silent_expected": expected.silent,
            "transcript": heard,
            "segments": [{"start": a, "end": b, "text": t} for a, b, t in segments],
            "ok": verdict.ok, "reason": verdict.reason,
            "overlap": verdict.overlap,
            "missing": verdict.missing, "extras": verdict.extras,
        }
        if args.emit_srt and segments:
            zh_lines = [zh_map[l] for l in expected.lines if l in zh_map]
            best_i, best_score = -1, 0.0
            if zh_lines:
                pool = set(re.sub(r"[^a-z0-9 ]", "", " ".join(expected.lines).lower()).split())
                for i, (_a, _b, text) in enumerate(segments):
                    st = set(re.sub(r"[^a-z0-9 ]", "", text.lower()).split())
                    score = len(st & pool) / max(1, len(st))
                    if score > best_score:
                        best_i, best_score = i, score
            out_lines: list[str] = []
            for i, (a, b, text) in enumerate(segments, 1):
                out_lines += [str(i), f"{_ts(a)} --> {_ts(b)}", text]
                if i - 1 == best_i and best_score > 0.3:
                    out_lines.append(zh_lines[0])
                out_lines.append("")
            mp4.with_suffix(".srt").write_text("\n".join(out_lines), encoding="utf-8")
        rows.append(row)
        flag = "PASS" if verdict.ok else "FAIL"
        print(f"{flag} {stem} {verdict.reason} overlap={verdict.overlap} "
              f"exp={len(expected.lines)} missing={len(verdict.missing)} "
              f"extras={len(verdict.extras)}", flush=True)
        for m in verdict.missing:
            print(f"    MISSING: {m[:100]}")
        for e in verdict.extras:
            print(f"    EXTRA: {e[:100]}")

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    bad = [r for r in rows if not r["ok"]]
    print(f"\nchecked={len(rows)} pass={len(rows)-len(bad)} fail={len(bad)} "
          f"report={args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
