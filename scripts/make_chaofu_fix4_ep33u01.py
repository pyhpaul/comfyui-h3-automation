#!/usr/bin/env python3
"""Build EP33-U01 -fix4: per-shot duration anchors on top of fix3.

Five wenxi renders fail identically: Sienna's close-up runs ~5 s for a
1.5 s question, and the model fills the leftover time by speaking
Cole's answer in her voice (F0 219 Hz), then Cole repeats it. fix3's
silent Danny buffer was executed by the model but did not help — the
fill happens inside her shot. Fix4 anchors each shot's duration and
ends her shot decisively (asks, turns to the float board, shot ends).
Dialogue text untouched.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "jobs" / "ep_units"

APPENDS: dict[int, str] = {
    2: "（本镜约两秒）问完立刻转头看向脚边的浮板，不再开口，本镜随即结束。",
    4: "（本镜约六秒）",
}


def main() -> int:
    src = next(SRC_DIR.glob("EP33-潮缚-fix3-U01"))
    dst = SRC_DIR / "EP33-潮缚-fix4-U01"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    (dst / "assets" / "prompt_audit.json").unlink(missing_ok=True)
    p = dst / "assets" / "prompt_source.txt"
    lines = p.read_text(encoding="utf-8").split("\n")
    shot_no = 0
    out = []
    for line in lines:
        if line.startswith("▲"):
            shot_no += 1
            if shot_no in APPENDS:
                line = line.rstrip() + APPENDS[shot_no]
                print(f"shot{shot_no}: appended duration anchor")
        out.append(line)
    assert shot_no == 4, f"expected 4 shots, got {shot_no}"
    p.write_text("\n".join(out), encoding="utf-8")
    print(f"EP33-U01: fix4 built {src.name} -> {dst.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
