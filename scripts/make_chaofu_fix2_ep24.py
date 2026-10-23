"""EP24 fix2: fix1 (night lock + dialogue locks) plus a hard exposure lock.

fix1 renders still drift to dusk (sky luma 0.19-0.31). Append an exposure
sentence at the end of the 【氛围与画质】 paragraph so the model cannot
keep blue/grey sky light. Dialogue text untouched.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "jobs" / "ep_units"

EXPOSURE_LOCK = (
    "整体画面曝光明显压暗，阴影暗部接近纯黑；"
    "天空与海面不允许出现蓝色、灰色或任何天光亮度，"
    "画面中唯一可见的光源就是门廊灯的暖光。"
)


def main() -> int:
    for uu in ("U01", "U02"):
        src = SRC_ROOT / f"EP24-潮缚-fix1-{uu}"
        dst = SRC_ROOT / f"EP24-潮缚-fix2-{uu}"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        (dst / "assets" / "prompt_audit.json").unlink(missing_ok=True)
        p = dst / "assets" / "prompt_source.txt"
        text = p.read_text(encoding="utf-8")
        if EXPOSURE_LOCK in text:
            print(f"EP24-{uu}: already locked")
            continue
        m = re.search(r"(【氛围与画质】[^\n]*)", text)
        if not m:
            print(f"EP24-{uu}: !! no 氛围 paragraph")
            return 1
        text = text.replace(m.group(1), m.group(1).rstrip() + EXPOSURE_LOCK, 1)
        p.write_text(text, encoding="utf-8")
        print(f"EP24-{uu}: exposure-lock appended")
    return 0


if __name__ == "__main__":
    sys.exit(main())
