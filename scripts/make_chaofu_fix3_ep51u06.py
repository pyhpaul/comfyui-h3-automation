#!/usr/bin/env python3
"""Build EP51-U06 -fix3: per-shot duration anchors on top of fix2.

Six attempts fail in the first exchange: Victor's short third line
("Say that again.") leaks into the opening shots (once garbled as a
mumbled rehearsal), then is spoken again in place. Shots render
compressed (4 planned, ~3 executed). Fix3 anchors each shot's
duration and declares the short line not-yet-spoken before its shot.
Dialogue text untouched.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "jobs" / "ep_units"

APPENDS: dict[int, str] = {
    1: "（本镜约四秒）本镜只有这一句台词，后面三句都还没有说出。",
    2: "（本镜约三秒）本镜只有这一句台词，说完不得提前说出后面的台词。",
    3: "（本镜约三秒）这句台词在前面任何镜头里都没有出现过，"
       "这是它第一次也是唯一一次被说出。",
    4: "（本镜约五秒）",
}


def main() -> int:
    src = next(SRC_DIR.glob("EP51-潮缚-fix2-U06"))
    dst = SRC_DIR / "EP51-潮缚-fix3-U06"
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
    print(f"EP51-U06: fix3 built {src.name} -> {dst.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
