#!/usr/bin/env python3
"""Build -fix2 jobs for EP33-U01 / EP42-U02 / EP42-U04.

Supplementary per-shot audit of the shipped wenxi versions found the
same wrong-speaker class again:
- EP33-U01: Cole's line is first spoken by Sienna (female F0 193 Hz on
  her close-up), then repeated by Cole (121 Hz). Her shot runs long and
  she mouths/speaks his line.
- EP42-U02: Victor's line plays over Wade's close-up while Wade's mouth
  opens/closes like speech (prompt literally said "嘴张了张没出声").
- EP42-U04: line tail lands on Wade's crying close-up with garbled
  vocalisation; Wade mouths while supposedly silent.

Fixes (dialogue text untouched):
- speaking shots: line spoken once, inside this shot only, then lips
  closed and silent until the shot ends; next line declared not yet
  spoken by anyone.
- silent shots: mouth-open beats replaced/pinned to lips sealed, no
  sobbing or throat sounds.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "jobs" / "ep_units"

# unit -> (replacements, {shot_no: append})
FIXES: dict[str, tuple[list[tuple[str, str]], dict[int, str]]] = {
    "EP33-U01": (
        [],
        {
            2: "本句只说一遍，说完立刻合上嘴唇，保持沉默，直到本镜结束；"
               "不得替别人说出下一句台词。",
            3: "这句台词全片只在本镜说这一次，前面没有任何人说过它；"
               "说完合上嘴唇，保持沉默，直到本镜结束。",
            4: "嘴唇只动一下随即紧紧闭上，全程不发出任何声音。",
        },
    ),
    "EP42-U02": (
        [("嘴张了张没出声", "嘴唇紧紧闭着、没有出声")],
        {
            1: "本镜一直持续到整句台词全部说完；说完后嘴唇合上，保持沉默。",
            2: "全程嘴唇紧闭、不动唇、不张嘴、不发出任何声音。",
        },
    ),
    "EP42-U04": (
        [],
        {
            3: "整句台词必须在本镜内全部说完，最后一个词也说在本镜里，"
               "不得把尾音拖到下一镜；说完嘴唇合上，保持沉默。",
            4: "即使眼眶发红、落泪，双唇也全程紧闭，不张嘴、不动唇、"
               "不发出抽泣或哽咽声，只有环境声。",
        },
    ),
}


def main() -> int:
    for unit, (replaces, appends) in FIXES.items():
        ep, uu = unit.split("-")
        src = next(SRC_DIR.glob(f"{ep}-潮缚-fix1-{uu}"))
        dst = SRC_DIR / f"{ep}-潮缚-fix2-{uu}"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        (dst / "assets" / "prompt_audit.json").unlink(missing_ok=True)
        p = dst / "assets" / "prompt_source.txt"
        text = p.read_text(encoding="utf-8")
        for old, new in replaces:
            assert old in text, f"{unit}: replace target not found: {old}"
            text = text.replace(old, new)
            print(f"{unit}: replaced {old!r}")
        lines = text.split("\n")
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
