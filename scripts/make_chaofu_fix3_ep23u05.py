#!/usr/bin/env python3
"""Build EP23-U05 -fix3: kill the invented tail monologue.

Every render speaks Cole's single line cleanly, then fills the
remaining ~8 s with low mumbled fake speech (ASR garble, speech-level
energy). The hand-off text describes Wade as "about to open his
mouth", and the model acts that out with improvised dialogue in
invented tail shots. Fix3 pins the tail: slow push stays on Cole,
absolute silence after the line, mumbling/whispering explicitly
banned. Dialogue text untouched.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "jobs" / "ep_units"

APPEND = (
    "说完后镜头继续缓慢推近Cole Mercer的脸，停留在他沉默的脸上直到本条结束，"
    "不得切换到其他镜头。台词结束后音频轨绝对安静：禁止喃喃低语、"
    "禁止含混不清的假台词、禁止任何人声，只有海风和门廊灯的细微电流声。"
    "Wade Mercer全程不发声、不动唇，他正要开口只表现为身体微微前倾，嘴唇始终闭着。"
)


def main() -> int:
    src = next(SRC_DIR.glob("EP23-潮缚-fix2-U05"))
    dst = SRC_DIR / "EP23-潮缚-fix3-U05"
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
            if shot_no == 1:
                line = line.rstrip() + APPEND
                print("shot1: appended anti-mumble tail lock")
        out.append(line)
    assert shot_no == 1, f"expected 1 shot, got {shot_no}"
    p.write_text("\n".join(out), encoding="utf-8")
    print(f"EP23-U05: fix3 built {src.name} -> {dst.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
