#!/usr/bin/env python3
"""Per-unit dialogue QC for lihun v23 Colab output (pieces 5+6 of 6).

Reads one rendered unit dir (mp4 pulled from Drive by the host), ASRs
it, scores against the job's prompt_source.txt （） lines, writes the
word-track .srt and dialogue_check.json beside the mp4, and uploads
both to the unit's Feiniu folder via add_qc_files. Appends one row to
the rolling report. Usage:

  PYTHONPATH=src python scripts/ops/qc_lihun_unit.py EP01-U01 \
    --unit-dir .cache/colab_wenxi_setup/<session>/units/EP01-U01
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
from comfy_orch.feiniu_archive import add_qc_files  # noqa: E402

BATCH = "离婚后（10.22）"
ROLLING = ROOT / "runs/dialogue_check_lihun_v23_rolling.md"
_ASSET_CODE = re.compile(r"（(?:W-|CREATURE-|scene-|char-|prop-)[^）]*）")


def _ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tag", help="EP01-U01")
    ap.add_argument("--unit-dir", type=Path, required=True)
    ap.add_argument("--no-upload", action="store_true")
    args = ap.parse_args()

    ep, unit = args.tag.split("-")
    # Fix-round candidates are tagged UxxC1…; prompt lives on the base unit job.
    base_unit = re.sub(r"C\d+$", "", unit)
    job = ROOT / "jobs/ep_units" / f"{ep}-继母-v23-{base_unit}"
    mp4s = sorted(args.unit_dir.glob("*.mp4"))
    if len(mp4s) != 1:
        raise SystemExit(f"{args.tag}: mp4s={mp4s}")
    mp4 = mp4s[0]
    source = _ASSET_CODE.sub(
        "", (job / "assets/prompt_source.txt").read_text(encoding="utf-8"))
    expected = extract_expected_dialogue(source)
    with tempfile.TemporaryDirectory(prefix="h3-dlg-") as tmp:
        wav = Path(tmp) / "audio.wav"
        mp4_to_wav(mp4, wav)
        heard, segments = transcribe_wav_faster_whisper(wav)
    verdict = score_transcript(heard=heard, segments=segments,
                               expected=expected)
    row = {
        "video": mp4.name, "episode": ep, "unit": unit,
        "expected_lines": expected.lines, "silent_expected": expected.silent,
        "transcript": heard,
        "segments": [{"start": a, "end": b, "text": t} for a, b, t in segments],
        "ok": verdict.ok, "reason": verdict.reason,
        "overlap": verdict.overlap,
        "missing": verdict.missing, "extras": verdict.extras,
    }
    srt_name = mp4.stem + ".srt"
    srt = "".join(
        f"{i}\n{_ts(a)} --> {_ts(b)}\n{t}\n\n"
        for i, (a, b, t) in enumerate(segments, 1))
    (args.unit_dir / srt_name).write_text(srt, encoding="utf-8")
    report_name = "dialogue_check.json"
    report_payload = (json.dumps(row, ensure_ascii=False, indent=2) + "\n").encode()
    (args.unit_dir / report_name).write_bytes(report_payload)
    status = "PASS" if verdict.ok else "FAIL"
    print(f"{status} {args.tag} overlap={verdict.overlap} "
          f"missing={verdict.missing} reason={verdict.reason}", flush=True)
    if not args.no_upload:
        remote = add_qc_files(srt_name, srt.encode("utf-8"), report_payload,
                              batch=BATCH, episode=ep, unit=f"{unit}-WENXI")
        print(f"QC_FEINIU {args.tag} -> {remote}", flush=True)
    ROLLING.parent.mkdir(parents=True, exist_ok=True)
    if not ROLLING.is_file():
        ROLLING.write_text(
            "# 离婚后 v23 Colab 生产对白滚动审核（EP01起）\n\n"
            "| 单元 | 判定 | overlap | missing | 备注 |\n"
            "|---|---|---|---|---|\n", encoding="utf-8")
    with ROLLING.open("a", encoding="utf-8") as f:
        f.write(f"| {args.tag} | {status} | {verdict.overlap} | "
                f"{verdict.missing} | {verdict.reason or ''} |\n")
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
