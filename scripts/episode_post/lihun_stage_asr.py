#!/usr/bin/env python3
"""Stage one lihun EP from Feiniu archive + optional fix winners, then CUDA ASR + dialogue_check."""
from __future__ import annotations

import argparse
import glob
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from comfy_orch.feiniu_archive import SHARE, connect_feiniu  # noqa: E402
from comfy_orch.dialogue_gate import extract_expected_dialogue, score_transcript  # noqa: E402


def smb_get(smb, remote: str) -> bytes:
    buf = io.BytesIO()
    smb.getFile(SHARE, remote, buf.write)
    return buf.getvalue()


def stage(ep: str, swaps: dict[str, str]) -> Path:
    """swaps: unit -> tag like U01 -> C1"""
    edit = ROOT / f".cache/lihun_{ep.lower()}_edit"
    archive = fr"H3_comfyUI_5090\archive\离婚后（10.22）\{ep}"
    if edit.exists():
        shutil.rmtree(edit)
    (edit / "inputs").mkdir(parents=True)
    (edit / "analysis").mkdir()
    smb = connect_feiniu()
    units = sorted(
        f.get_longname().replace("-WENXI", "")
        for f in smb.listPath(SHARE, archive + "\\*")
        if f.get_longname().endswith("-WENXI")
    )
    sources = {}
    for u in units:
        udir = edit / "inputs" / f"{ep}-{u}"
        udir.mkdir()
        if u in swaps:
            tag = swaps[u]
            local = ROOT / f".cache/lihun_v23_fix1_review/{ep}-{u}/{tag}"
            # Feiniu: .../EPxx/EPxx-UyyCz/  or older .../EPxx/Uyy/
            fix_candidates = [
                fr"H3_comfyUI_5090\archive\离婚后修复定版（10.22）\文戏工作流\{ep}\{ep}-{u}{tag}",
                fr"H3_comfyUI_5090\archive\离婚后修复定版（10.22）\文戏工作流\{ep}\{u}",
            ]
            mp4_name = f"{ep}-{u}{tag}-lihun-wenxi_00001-audio.mp4"

            def pull_fix(name: str) -> bytes:
                last = None
                for fix in fix_candidates:
                    try:
                        return smb_get(smb, fix + "\\" + name)
                    except Exception as exc:  # noqa: BLE001
                        last = exc
                raise RuntimeError(f"fix asset missing {ep}-{u}{tag}/{name}: {last}")

            if (local / mp4_name).is_file():
                data = (local / mp4_name).read_bytes()
                prompt = (
                    (local / "prompt_h3.txt").read_bytes()
                    if (local / "prompt_h3.txt").is_file()
                    else pull_fix("prompt_h3.txt")
                )
            else:
                data = pull_fix(mp4_name)
                prompt = pull_fix("prompt_h3.txt")
            try:
                meta = pull_fix("run_meta.json")
            except Exception:
                meta = smb_get(smb, archive + f"\\{u}-WENXI\\run_meta.json")
            (udir / mp4_name).write_bytes(data)
            (udir / "prompt_h3.txt").write_bytes(prompt)
            (udir / "run_meta.json").write_bytes(meta)
            sources[u] = {"kind": "fix_winner", "file": mp4_name, "tag": tag}
            print("staged fix", u, tag, flush=True)
        else:
            rd = archive + f"\\{u}-WENXI"
            names = [n.get_longname() for n in smb.listPath(SHARE, rd + "\\*") if n.get_longname() not in (".", "..")]
            mp4 = next(n for n in names if n.endswith(".mp4"))
            (udir / mp4).write_bytes(smb_get(smb, rd + "\\" + mp4))
            (udir / "prompt_h3.txt").write_bytes(smb_get(smb, rd + "\\prompt_h3.txt"))
            (udir / "run_meta.json").write_bytes(smb_get(smb, rd + "\\run_meta.json"))
            sources[u] = {"kind": "archive", "file": mp4}
            print("staged archive", u, mp4, flush=True)
    smb.close()
    meta = {"episode": ep, "fix_swap": swaps, "unit_order": units, "sources": sources}
    (edit / "stage_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    print("STAGE_OK", edit, units, flush=True)
    return edit


def asr_all(edit: Path) -> None:
    cands = glob.glob(str(Path.home() / "/.local/lib/python*/site-packages/nvidia/*/lib"))
    cands += glob.glob(str(ROOT / ".worktrees/feat-orch/.venv/lib/python*/site-packages/nvidia/*/lib"))
    os.environ["LD_LIBRARY_PATH"] = ":".join(cands) + (
        (":" + os.environ["LD_LIBRARY_PATH"]) if os.environ.get("LD_LIBRARY_PATH") else ""
    )
    from faster_whisper import WhisperModel

    model = WhisperModel("small", device="cuda", compute_type="float16")
    inputs = sorted((edit / "inputs").glob("EP*-U*"), key=lambda p: int(p.name.split("-U")[1]))
    for ud in inputs:
        mp4 = next(ud.glob("*.mp4"))
        expected = extract_expected_dialogue((ud / "prompt_h3.txt").read_text(encoding="utf-8"))
        print("ASR", mp4.name, "n", len(expected.lines), flush=True)
        segments, info = model.transcribe(str(mp4), language="en", word_timestamps=True, vad_filter=True)
        rows = [
            {
                "start": s.start,
                "end": s.end,
                "text": s.text.strip(),
                "words": [{"start": w.start, "end": w.end, "word": w.word} for w in (s.words or [])],
            }
            for s in segments
        ]
        sha = hashlib.sha256(mp4.read_bytes()).hexdigest()
        ana = {
            "source": str(mp4.resolve()),
            "sha256": sha,
            "model": "small",
            "language": info.language,
            "duration": info.duration,
            "segments": rows,
        }
        (edit / "analysis" / (mp4.stem + ".json")).write_text(
            json.dumps(ana, ensure_ascii=False, indent=2) + "\n"
        )
        segs = [(r["start"], r["end"], r["text"]) for r in rows]
        heard = " ".join(r["text"] for r in rows)
        v = score_transcript(heard=heard, segments=segs, expected=expected)
        dc = {
            "ok": v.ok,
            "reason": v.reason,
            "overlap": v.overlap,
            "missing": list(v.missing),
            "extras": list(v.extras),
            "expected_lines": expected.lines,
            "transcript": heard,
            "segments": [{"start": a, "end": b, "text": t} for a, b, t in segs],
        }
        (ud / "dialogue_check.json").write_text(json.dumps(dc, ensure_ascii=False, indent=2) + "\n")
        fr = subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
                "-show_entries", "stream=nb_read_frames,duration", "-of", "csv=p=0", str(mp4),
            ],
            text=True,
        ).strip()
        print(
            " ",
            "PASS" if v.ok else "FAIL",
            v.reason,
            "ov",
            v.overlap,
            "miss",
            v.missing,
            "extra",
            [e[:40] for e in v.extras],
            "frames",
            fr,
            flush=True,
        )
        for s in rows:
            print(f"    {s['start']:.2f}-{s['end']:.2f} {s['text'][:75]}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("--swap", action="append", default=[], help="U01=C1")
    args = ap.parse_args()
    swaps = {}
    for item in args.swap:
        u, tag = item.split("=", 1)
        swaps[u] = tag
    edit = stage(args.episode, swaps)
    asr_all(edit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
