#!/usr/bin/env python3
"""Build EP51-U06 -fix2 job: kill the first-exchange line doubling.

Every render (chained loop, 3x independent) doubles one of the first
two lines. The prompt is already single-person-per-shot with a
whitelist lock, but shot 2 literally ends with "说完，嘴还没合上"
(mouth still open after speaking) — an invitation to keep talking.
Fix2:
- shot 2: mouth-open ending replaced with lips-closed.
- every speaking shot: silent beat before speaking, line spoken once,
  then lips closed and silent until the shot ends.
Dialogue text itself is untouched.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "jobs" / "ep_units"

REPLACE = (
    "Wade Mercer说完，嘴还没合上，眼神已经虚了",
    "Wade Mercer说完立刻闭上嘴唇，眼神发虚",
)

APPENDS: dict[int, str] = {
    1: "开口前先沉默一秒，指节压桌、一动不动；本句只说一遍，"
       "说完立刻合上嘴唇，保持沉默，直到本镜结束。",
    2: "开口前先撇嘴沉默一秒；本句只说一遍，说完嘴唇紧闭，"
       "保持沉默，直到本镜结束。",
    3: "本句只说一遍，说完嘴唇紧闭，保持沉默，直到本镜结束。",
    4: "本句只说一遍，说完嘴唇紧闭，保持沉默，直到本镜结束；"
       "不得重复前面说过的话。",
}


def main() -> int:
    src = next(SRC_DIR.glob("EP51-潮缚-fix1-U06"))
    dst = SRC_DIR / "EP51-潮缚-fix2-U06"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    (dst / "assets" / "prompt_audit.json").unlink(missing_ok=True)
    p = dst / "assets" / "prompt_source.txt"
    text = p.read_text(encoding="utf-8")
    old, new = REPLACE
    assert old in text, "mouth-open ending not found"
    text = text.replace(old, new)
    print("shot2: mouth-open ending replaced")
    lines = text.split("\n")
    shot_no = 0
    out = []
    for line in lines:
        if line.startswith("▲"):
            shot_no += 1
            if shot_no in APPENDS:
                line = line.rstrip() + APPENDS[shot_no]
                print(f"shot{shot_no}: appended pacing lock")
        out.append(line)
    assert shot_no == 4, f"expected 4 shots, got {shot_no}"
    p.write_text("\n".join(out), encoding="utf-8")
    print(f"EP51-U06: fix2 built from {src.name} -> {dst.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
