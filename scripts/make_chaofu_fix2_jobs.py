#!/usr/bin/env python3
"""Build -fix2 copies for units whose repetition is structure-driven.

EP50-U02: line 1 repeats in every render (both chains). Shot 1 is a
silent Victor reaction, Sienna's line starts at shot 2 — the model
starts her line during shot 1 and says it again in shot 2. Fix2 pins
shot 1 to total silence and declares the line single-occurrence.

EP41-U05: Wade's consecutive lines loop (whole block repeats). Fix2
pins each Wade shot to its own line only.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "jobs" / "ep_units"

# unit -> {shot_no: text to append to that ▲ paragraph}
APPENDS: dict[str, dict[int, str]] = {
    "EP50-U02": {
        1: "本镜全程没有任何对白，只有环境声；Sienna Harlow不入画、不发声，"
           "不得提前说出后面的台词。",
        2: "这句台词全片只在本镜说这一次，前面的镜头里没有人说过它，"
           "后面也不得再重复。",
    },
    "EP41-U05": {
        3: "本镜只说这一句，说完立刻闭嘴，不得接着说下一句。",
        4: "本镜只说这一句，不得重复前面已经说过的话。",
    },
}


def main() -> int:
    for unit, shots in APPENDS.items():
        ep, uu = unit.split("-")
        src = next(SRC.glob(f"{ep}-潮缚-fix1-{uu}"))
        dst = SRC / f"{ep}-潮缚-fix2-{uu}"
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
                if shot_no in shots:
                    line = line.rstrip() + shots[shot_no]
                    print(f"{unit} shot{shot_no}: appended lock")
            out.append(line)
        p.write_text("\n".join(out), encoding="utf-8")
        print(f"{unit}: fix2 built from {src.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
