#!/usr/bin/env python3
"""Audit-first verification for Chaofu fix1 renders.

Workflow (per user instruction 2026-10-20): renders land LOCALLY first;
only units that pass audit are uploaded to Feiniu.

Modes:
  audit (default): for each unit x {orig, wenxi}, take the mp4 from the
    local verify dir (--local) or pull it from the Feiniu batch, run ASR
    vs script lines, extract per-segment frames (speaker attribution is
    judged by a human/agent from those frames), EP24 night-luma samples.
  ship (--attribution UNIT:version=PASS): additionally write
    dialogue_check.md (bilingual audit) + <stem>.srt (bilingual word
    track) next to the local mp4; with --ship-canonical also upload the
    four canonical files (mp4/latent/prompt_h3/run_meta) — use only for
    units whose local dir holds a not-yet-uploaded render.

Usage:
  PYTHONPATH=src python scripts/ops/verify_chaofu_fix1.py --local \
      --units EP06-U04
  PYTHONPATH=src python scripts/ops/verify_chaofu_fix1.py --local \
      --units EP06-U04 --attribution EP06-U04:wenxi=PASS --ship-canonical
"""
from __future__ import annotations

import argparse
import io
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
from comfy_orch.feiniu_archive import archive_named_files  # noqa: E402

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


def job_dir(unit: str) -> Path:
    ep, uu = unit.split("-")
    kind = "fix1" if (ROOT / "jobs/ep_units" / f"{ep}-潮缚-fix1-{uu}").exists() else "v1"
    return ROOT / "jobs/ep_units" / f"{ep}-潮缚-{kind}-{uu}"


def grab(mp4: Path, t: float, out: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i",
         str(mp4), "-frames:v", "1", "-vf", "scale=360:-1", str(out)],
        check=True)


def sky_luma(mp4: Path, t: float) -> float:
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-ss", f"{t}", "-i", str(mp4),
         "-frames:v", "1", "-vf", "crop=iw:ih/4:0:0,format=gray",
         "-f", "rawvideo", "-"],
        check=True, capture_output=True).stdout
    return sum(raw) / len(raw) / 255.0 if raw else -1.0


def probe(mp4: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height",
         "-of", "json", str(mp4)],
        check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def _ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def emit_srt(segments, expected_lines, zh_map) -> str:
    exp_norm = {_norm(l): l for l in expected_lines}
    blocks = []
    for i, (a, b, text) in enumerate(segments, 1):
        text = (text or "").strip()
        if not text:
            continue
        tset = set(_norm(text).split())
        best, best_zh = 0.0, ""
        for norm_line, orig in exp_norm.items():
            eset = set(norm_line.split())
            if not eset:
                continue
            ov = len(tset & eset) / max(1, len(tset))
            if ov > best:
                best, best_zh = ov, zh_map.get(orig, "")
        lines = [str(i), f"{_ts(a)} --> {_ts(b)}", text]
        if best >= 0.4 and best_zh:
            lines.append(best_zh)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def audit(unit: str, version: str, mp4: Path, local_dir: Path) -> dict:
    row: dict = {"mp4": mp4.name, "probe": probe(mp4)}
    frames = local_dir / "frames"
    frames.mkdir(exist_ok=True)
    if unit in DIALOGUE_UNITS:
        src = (job_dir(unit) / "assets" / "prompt_source.txt").read_text(
            encoding="utf-8")
        expected = extract_expected_dialogue(_ASSET_CODE.sub("", src))
        with tempfile.TemporaryDirectory() as td:
            wav = Path(td) / "a.wav"
            mp4_to_wav(mp4, wav)
            heard, segments = transcribe_wav_faster_whisper(wav)
        verdict = score_transcript(
            heard=heard, segments=segments, expected=expected)
        row["asr"] = {
            "ok": verdict.ok, "reason": verdict.reason,
            "overlap": verdict.overlap, "heard": heard,
            "expected": expected.lines,
            "segments": [{"start": a, "end": b, "text": t}
                         for a, b, t in segments],
        }
        for i, (a, b, _t) in enumerate(segments):
            grab(mp4, (a + b) / 2.0, frames / f"seg{i}.png")
    if unit in EP24_UNITS:
        row["sky_luma_top"] = [
            round(sky_luma(mp4, t), 3) for t in (2.0, 7.0, 12.0)]
        for j, t in enumerate((2.0, 7.0, 12.0)):
            grab(mp4, t, frames / f"night{j}.png")
    if unit in EP62_UNITS or unit in EP63_UNITS:
        for j, t in enumerate((2.0, 7.0, 12.0)):
            grab(mp4, t, frames / f"t{j}.png")
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=ROOT / ".cache" / "chaofu_fix1_verify")
    ap.add_argument("--units", nargs="+", default=None)
    ap.add_argument("--local", action="store_true",
                    help="mp4s already under --out (not on Feiniu yet)")
    ap.add_argument("--attribution", action="append", default=[],
                    help="UNIT:version=PASS|FAIL (frame-review verdict)")
    ap.add_argument("--ship-canonical", action="store_true",
                    help="with --attribution=PASS also upload canonical 4")
    args = ap.parse_args()
    attribution = {}
    for item in args.attribution:
        key, _, verdict = item.partition("=")
        attribution[key] = verdict
    zh_map = json.loads((ROOT / "scripts/ops/chaofu_zh_map.json")
                        .read_text(encoding="utf-8"))
    units = args.units or ALL_UNITS
    args.out.mkdir(parents=True, exist_ok=True)

    pw = Path("/home/linux_dev/.config/fnos/ai.pass").read_text().strip()
    conn = SMBConnection("192.168.60.103", "192.168.60.103",
                         sess_port=445, timeout=120)
    conn.login("ai", pw)
    base = f"H3_comfyUI_5090/archive/{BATCH}"

    report_path = args.out / "report.json"
    report = (json.loads(report_path.read_text())
              if report_path.exists() else {})

    for unit in units:
        ep, uu = unit.split("-")
        report.setdefault(unit, {})
        for version, udir in [("orig", uu), ("wenxi", f"{uu}-WENXI")]:
            local_dir = args.out / unit / version
            local_dir.mkdir(parents=True, exist_ok=True)
            remote = f"{base}/{ep}/{udir}"
            if args.local:
                mp4s = sorted(local_dir.glob("*-audio.mp4"))
                if not mp4s:
                    continue
                mp4 = mp4s[-1]
            else:
                try:
                    entries = conn.listPath(SHARE, remote + "/*")
                except Exception:  # noqa: BLE001
                    print(f"{unit}/{version}: MISSING DIR")
                    report[unit][version] = {"error": "missing dir"}
                    continue
                names = sorted(e.get_longname() for e in entries
                               if e.get_longname().endswith("-audio.mp4"))
                if not names:
                    report[unit][version] = {"error": "no mp4"}
                    continue
                mp4 = local_dir / names[-1]
                if not mp4.exists():
                    with open(mp4, "wb") as fh:
                        conn.getFile(SHARE, f"{remote}/{names[-1]}", fh.write)
            row = audit(unit, version, mp4, local_dir)
            report[unit][version] = row
            print(f"{unit}/{version}: asr={row.get('asr', {}).get('reason', '-')} "
                  f"luma={row.get('sky_luma_top', '-')}")

            key = f"{unit}:{version}"
            if key not in attribution:
                continue
            # write bilingual audit + SRT, then ship
            asr = row["asr"]
            segments = [(s["start"], s["end"], s["text"])
                        for s in asr["segments"]]
            stem = mp4.stem.replace("-audio", "")
            srt = emit_srt(segments, asr["expected"], zh_map)
            exp_block = "\n".join(
                f"- {l}（{zh_map.get(l, '')}）" for l in asr["expected"])
            seg_block = "\n".join(
                f"- [{_ts(a)}] {t}（{zh_map.get(t, '')}）"
                for a, _b, t in segments)
            md = (f"# 对白识别审核 {unit}（{version}）\n\n"
                  f"## 剧本台词（期望）\n{exp_block}\n\n"
                  f"## 识别听到（英）\n{asr['heard']}\n\n"
                  f"## 逐段\n{seg_block}\n\n"
                  f"## 判定\n"
                  f"- 台词内容（ASR）：{asr['reason']}"
                  f"（重合度 {asr['overlap']}）\n"
                  f"- 说话人归属（逐段帧审）：{attribution[key]}\n")
            (local_dir / "dialogue_check.md").write_text(md, encoding="utf-8")
            (local_dir / f"{stem}.srt").write_text(srt, encoding="utf-8")
            if attribution[key] != "PASS":
                print(f"{unit}/{version}: FAIL — not shipped")
                continue
            if args.ship_canonical:
                payloads = {}
                for f in local_dir.iterdir():
                    if f.suffix in (".mp4", ".safetensors") or \
                            f.name in ("prompt_h3.txt", "run_meta.json"):
                        payloads[f.name] = f.read_bytes()
                remote_dir = archive_named_files(
                    payloads, batch=BATCH,
                    episode=f"{ep}-潮缚-v1", unit=udir, smb=conn)
                print(f"{unit}/{version}: canonical -> {remote_dir}")
            for name in ("dialogue_check.md", f"{stem}.srt"):
                data = (local_dir / name).read_bytes()
                conn.putFile(SHARE, f"{remote}/{name}",
                             io.BytesIO(data).read)
            print(f"{unit}/{version}: audit assets uploaded")
    conn.logoff()
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print("report ->", report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
