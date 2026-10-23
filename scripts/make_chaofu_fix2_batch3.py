#!/usr/bin/env python3
"""Build -fix2 jobs for EP23-U01 / EP23-U05 / EP06-U04.

Strict re-audit (per-shot frames + audio energy) of shipped versions:
- EP23-U01 wenxi: Cole keeps talking into the next line's territory
  (partial repeat), Wade then says the full line again.
- EP23-U05 both chains: after Cole's single line, the model invents
  extra mumbled speech (speech-level RMS in "silent" windows). The
  prompt has one speaking shot; renders improvise extra cuts/lines.
- EP06-U04 orig: Wade delivers Cole's opening line (again). Wenxi is
  PASS; this fix2 is the prompt lever for the A-side re-render.

Dialogue text untouched; only mouth/pacing locks appended.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "jobs" / "ep_units"

FIXES: dict[str, dict[int, str]] = {
    "EP23-U01": {
        2: "本句只说这一句，说完立刻合上嘴唇，保持沉默，直到本镜结束；"
           "不得说出下一句台词里的任何一个词。",
        3: "这句台词全片只在本镜说这一次，前面没有任何人说过它；"
           "说完合上嘴唇，保持沉默，直到本镜结束。",
    },
    "EP23-U05": {
        1: "本句说完后画面保持在本镜，不得切换到其他镜头；全片只有"
           "这一句台词，此后任何人不得再发出任何语音，只有环境声。",
    },
    "EP06-U04": {
        1: "本镜自始至终只有Cole Mercer一个人入画，Wade Mercer不入画；"
           "只有Cole Mercer开口，本句只说一遍，说完合上嘴唇。",
        2: "不得替Cole Mercer说出任何台词。",
        3: "本句只说一遍，说完合上嘴唇，保持沉默，直到本镜结束。",
    },
}


def main() -> int:
    for unit, appends in FIXES.items():
        ep, uu = unit.split("-")
        src = next(SRC_DIR.glob(f"{ep}-潮缚-fix1-{uu}"))
        dst = SRC_DIR / f"{ep}-潮缚-fix2-{uu}"
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
                if shot_no in appends:
                    line = line.rstrip() + appends[shot_no]
                    print(f"{unit} shot{shot_no}: appended lock")
            out.append(line)
        p.write_text("\n".join(out), encoding="utf-8")
        print(f"{unit}: fix2 built {src.name} -> {dst.name} (shots={shot_no})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
