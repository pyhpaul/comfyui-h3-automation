#!/usr/bin/env python3
"""Build EP06-U04 -fix3: over-Wade's-shoulder opener for Cole's line.

Both chains keep handing Cole's opening block to Wade: renders open
on Wade's face and he delivers it (the original QC complaint). The
spatial hard lock already places Cole's frontal camera behind Wade;
fix3 makes shot 1 explicitly over-Wade's-shoulder — Wade appears only
as shoulder/back-of-head in the foreground and cannot mouth the line,
Cole faces camera and speaks. Dialogue text untouched.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "jobs" / "ep_units"

REPLACES = [
    (
        "▲固定镜头，近景［Cole Mercer正面，门边］。Cole Mercer的笑意收得干干净净",
        "▲固定镜头，近景［越过Wade Mercer的肩头，看向门边的Cole Mercer］。"
        "画面前景一侧是Wade Mercer的肩背和后脑，Wade Mercer不露正脸、嘴唇不动。"
        "Cole Mercer的笑意收得干干净净",
    ),
    (
        "本镜画面中只有Cole Mercer入画，其他人物不入画。"
        "入画者是Cole Mercer（穿深橄榄绿色工装夹克），不是Wade Mercer，"
        "不得把Cole Mercer的脸画成Wade Mercer。"
        "本镜自始至终只有Cole Mercer一个人入画，Wade Mercer不入画；只有Cole Mercer开口",
        "本镜只有Cole Mercer露正脸并开口，"
        "入画者是Cole Mercer（穿深橄榄绿色工装夹克），不是Wade Mercer，"
        "不得把Cole Mercer的脸画成Wade Mercer。"
        "Wade Mercer只以肩背和后脑入画，不露正脸、不开口；只有Cole Mercer开口",
    ),
]


def main() -> int:
    src = next(SRC_DIR.glob("EP06-潮缚-fix2-U04"))
    dst = SRC_DIR / "EP06-潮缚-fix3-U04"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    (dst / "assets" / "prompt_audit.json").unlink(missing_ok=True)
    p = dst / "assets" / "prompt_source.txt"
    text = p.read_text(encoding="utf-8")
    for old, new in REPLACES:
        assert old in text, f"replace target not found: {old[:40]}"
        text = text.replace(old, new, 1)
        print(f"replaced: {old[:36]}...")
    p.write_text(text, encoding="utf-8")
    print(f"EP06-U04: fix3 built {src.name} -> {dst.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
