#!/usr/bin/env python3
"""EP41-U05 fix4: insert a silent Victor reaction shot between Wade's
two consecutive lines.

Three dialogue lines in 15s loop in every render (orig, wenxi chained
x3, wenxi independent): the model restarts the block instead of
stopping. Fix4 breaks the loop with a silent reaction cutaway so each
line lands in its own shot with a breath between. Dialogue text is
unchanged; the inserted shot has no dialogue.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "jobs" / "ep_units" / "EP41-潮缚-fix2-U05"
DST = ROOT / "jobs" / "ep_units" / "EP41-潮缚-fix4-U05"

REACTION = (
    "▲固定镜头，近景［Victor Harlow正面，低头看着第二只箱子］。"
    "Victor Harlow低头看着箱子里的碎石，眉毛都没动一下，嘴唇合上、"
    "全程不动唇、不发声，只有海浪声和箱板碎裂的余响。"
    "本镜画面中只有Victor Harlow入画，其他人物不入画。"
)


def main() -> int:
    if DST.exists():
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST)
    (DST / "assets" / "prompt_audit.json").unlink(missing_ok=True)
    p = DST / "assets" / "prompt_source.txt"
    lines = p.read_text(encoding="utf-8").split("\n")
    out = []
    shot_no = 0
    inserted = False
    for line in lines:
        if line.startswith("▲"):
            shot_no += 1
            if shot_no == 4 and not inserted:
                out.append(REACTION)
                inserted = True
                print("reaction shot inserted before shot 4")
        out.append(line)
    if not inserted:
        raise SystemExit("shot 4 not found")
    p.write_text("\n".join(out), encoding="utf-8")
    print("fix4 built:", DST.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
