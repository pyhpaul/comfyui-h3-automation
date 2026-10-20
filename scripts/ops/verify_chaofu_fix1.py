#!/usr/bin/env python3
"""Post-render verification for the Chaofu fix1 dual renders.

For every fixed unit x {orig, wenxi} in Feiniu batch 潮缚修复（10.20）:
1. Pull the mp4 locally.
2. Dialogue units: ASR vs script （） lines (content + repetition), and
   extract one frame per ASR segment (midpoint) for speaker-attribution
   review (outfit-based, done by a human/agent looking at the frames).
3. EP24 units: sample 3 frames and measure sky-region luma (night check)
   plus keep frames for visual confirm.
4. EP62/EP63: completeness (duration/streams) + ASR when lines exist.

Writes .cache/chaofu_fix1_verify/report.json and prints a summary table.
Speaker attribution and night verdicts are filled in after frame review;
this script produces the evidence, not the final word.
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

from impacket.smbconnection import SMBConnection  # noqa: E402
from comfy_orch.dialogue_gate import (  # noqa: E402
    extract_expected_dialogue,
    mp4_to_wav,
    score_transcript,
    transcribe_wav_faster_whisper,
)

SHARE = "ai短剧同步文件夹"
BATCH = "潮缚修复（10.20）"
_ASSET_CODE = re.compile(r"（(?:W-|CREATURE-|scene-|char-|prop-)[^）]*）")

DIALOGUE_UNITS = [
    "EP06-U04", "EP23-U01", "EP23-U05", "EP33-U01", "EP41-U05",
    "EP42-U02", "EP42-U04", "EP43-U05", "EP50-U02", "EP51-U06",
    "EP53-U05", "EP24-U01", "EP24-U02",
]
EP24_UNITS = [f"EP24-U0{i}" for i in range(1, 7)]
EP62_UNITS = [f"EP62-U0{i}" for i in range(1, 8)]
EP63_UNITS = [f"EP63-U0{i}" for i in range(1, 7)]
ALL_UNITS = sorted(set(DIALOGUE_UNITS) | set(EP24_UNITS)
                   | set(EP62_UNITS) | set(EP63_UNITS))


def job_dir(unit: str, fix: bool) -> Path:
    ep, uu = unit.split("-")
    kind = "fix1" if fix else "v1"
    return next((ROOT / "jobs/ep_units").glob(f"{ep}-潮缚-{kind}-{uu}"))


def grab(mp4: Path, t: float, out: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i",
         str(mp4), "-frames:v", "1", "-vf", "scale=360:-1", str(out)],
        check=True)


def sky_luma(mp4: Path, t: float) -> float:
    """Mean luma of the top 25% of the frame (sky/background proxy)."""
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-ss", f"{t}", "-i", str(mp4),
         "-frames:v", "1", "-vf", "crop=iw:ih/4:0:0,format=gray",
         "-f", "rawvideo", "-"],
        check=True, capture_output=True).stdout
    if not raw:
        return -1.0
    return sum(raw) / len(raw) / 255.0


def probe(mp4: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height",
         "-of", "json", str(mp4)],
        check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=ROOT / ".cache" / "chaofu_fix1_verify")
    ap.add_argument("--units", nargs="+", default=None)
    args = ap.parse_args()
    units = args.units or ALL_UNITS
    args.out.mkdir(parents=True, exist_ok=True)

    pw = Path("/home/linux_dev/.config/fnos/ai.pass").read_text().strip()
    conn = SMBConnection("192.168.60.103", "192.168.60.103",
                         sess_port=445, timeout=120)
    conn.login("ai", pw)
    base = f"H3_comfyUI_5090/archive/{BATCH}"

    report: dict = {}
    for unit in units:
        ep, uu = unit.split("-")
        report[unit] = {}
        for version, udir in [("orig", uu), ("wenxi", f"{uu}-WENXI")]:
            remote = f"{base}/{ep}/{udir}"
            try:
                entries = conn.listPath(SHARE, remote + "/*")
            except Exception as exc:  # noqa: BLE001
                report[unit][version] = {"error": f"list {exc}"}
                print(f"{unit}/{version}: MISSING DIR")
                continue
            mp4s = sorted(e.get_longname() for e in entries
                          if e.get_longname().endswith("-audio.mp4"))
            if not mp4s:
                report[unit][version] = {"error": "no mp4"}
                print(f"{unit}/{version}: NO MP4")
                continue
            local_dir = args.out / unit / version
            local_dir.mkdir(parents=True, exist_ok=True)
            mp4 = local_dir / mp4s[-1]
            if not mp4.exists():
                with open(mp4, "wb") as fh:
                    conn.getFile(SHARE, f"{remote}/{mp4s[-1]}", fh.write)
            row: dict = {"mp4": mp4s[-1], "probe": probe(mp4)}

            frames = local_dir / "frames"
            frames.mkdir(exist_ok=True)
            if unit in DIALOGUE_UNITS:
                src = (job_dir(unit, fix=True) / "assets"
                       / "prompt_source.txt").read_text(encoding="utf-8")
                expected = extract_expected_dialogue(
                    _ASSET_CODE.sub("", src))
                with tempfile.TemporaryDirectory() as td:
                    wav = Path(td) / "a.wav"
                    mp4_to_wav(mp4, wav)
                    heard, segments = transcribe_wav_faster_whisper(wav)
                verdict = score_transcript(
                    heard=heard, segments=segments, expected=expected)
                row["asr"] = {
                    "ok": verdict.ok, "reason": verdict.reason,
                    "overlap": verdict.overlap, "heard": heard,
                    "segments": [{"start": a, "end": b, "text": t}
                                 for a, b, t in segments],
                }
                for i, (a, b, _t) in enumerate(segments):
                    grab(mp4, (a + b) / 2.0, frames / f"seg{i}.png")
            if unit in EP24_UNITS:
                lumas = []
                for j, t in enumerate([2.0, 7.0, 12.0]):
                    grab(mp4, t, frames / f"night{j}.png")
                    lumas.append(round(sky_luma(mp4, t), 3))
                row["sky_luma_top"] = lumas
            if unit in EP62_UNITS or unit in EP63_UNITS:
                for j, t in enumerate([2.0, 7.0, 12.0]):
                    grab(mp4, t, frames / f"t{j}.png")
            report[unit][version] = row
            asr = row.get("asr", {})
            print(f"{unit}/{version}: ok mp4={mp4s[-1]} "
                  f"asr={asr.get('reason', '-')} "
                  f"luma={row.get('sky_luma_top', '-')}")
    conn.logoff()
    (args.out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1))
    print("report ->", args.out / "report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
