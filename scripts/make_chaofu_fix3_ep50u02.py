#!/usr/bin/env python3
"""EP50-U02 fix3: remove the silent Victor opening shot.

Every render (orig + wenxi x3, incl. text-lock fix2) speaks Sienna's
first line twice: once over the opening shot, once in her close-up.
The silent-reaction opener invites the echo. Fix3 starts directly on
Sienna's speaking close-up (single-person shots throughout), folds the
camera numbering in 【空间／朝向硬锁】 to match, and drops Victor's
silent beat from 变化与落点 (his speaking shot keeps its own lead-in).
Dialogue lines themselves are untouched.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "jobs" / "ep_units" / "EP50-潮缚-fix1-U02"
DST = ROOT / "jobs" / "ep_units" / "EP50-潮缚-fix3-U02"


def main() -> int:
    if DST.exists():
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST)
    (DST / "assets" / "prompt_audit.json").unlink(missing_ok=True)
    p = DST / "assets" / "prompt_source.txt"
    text = p.read_text(encoding="utf-8")

    # 1) drop the silent Victor opening shot paragraph
    lines = text.split("\n")
    out = []
    dropped = False
    for line in lines:
        if (not dropped and line.startswith("▲")
                and "Victor Harlow没有接话" in line):
            dropped = True
            print("dropped silent opener shot")
            continue
        out.append(line)
    if not dropped:
        raise SystemExit("opener shot not found")
    text = "\n".join(out)

    # 2) renumber camera descriptions in the hard-lock paragraph
    old_cam = (
        "第一、三镜 Victor 正面近景机位在桌面西南段、Sienna 座位东南约一米、"
        "朝东北，背景是落地窗外的港口，北端主位在画左之外；"
        "第二镜 Sienna 正面近景机位在桌面东南段、Victor 座位西南约一米、"
        "朝西北，缓慢推近，背景是西墙，北端主位在画右之外；"
        "第四镜机位在 Victor 左肩后［他的南侧］、朝西偏北，越过他的左肩拍 Sienna。")
    new_cam = (
        "第一镜 Sienna 正面近景机位在桌面东南段、Victor 座位西南约一米、"
        "朝西北，缓慢推近，背景是西墙，北端主位在画右之外；"
        "第二镜 Victor 正面近景机位在桌面西南段、Sienna 座位东南约一米、"
        "朝东北，背景是落地窗外的港口，北端主位在画左之外；"
        "第三镜机位在 Victor 左肩后［他的南侧］、朝西偏北，越过他的左肩拍 Sienna。")
    if old_cam not in text:
        raise SystemExit("camera block not found")
    text = text.replace(old_cam, new_cam)
    print("cameras renumbered")

    # 3) drop Victor's silent beat at the start of 变化与落点
    old_beat = ("变化与落点：Victor 上身向北略扭，头向右回看东侧窗外，"
                "再把上身与头回正朝西、垂眼看桌面，两根手指压平；"
                "Sienna 上身向东前倾")
    if old_beat not in text:
        raise SystemExit("beat block not found")
    text = text.replace(old_beat, "变化与落点：Sienna 上身向东前倾")
    print("silent beat dropped")

    p.write_text(text, encoding="utf-8")
    print("fix3 built:", DST.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
