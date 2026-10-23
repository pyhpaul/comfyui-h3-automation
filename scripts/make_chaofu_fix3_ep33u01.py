#!/usr/bin/env python3
"""Build EP33-U01 -fix3 job: silent buffer shot between the speakers.

Three wenxi renders fail identically: Cole's long answer starts during
Sienna's close-up (she mouths/speaks it), then Cole repeats it in his
own shot. fix2's lips-closed locks did not stop the anticipation.
Fix3 moves Danny's silent reaction shot between Sienna's question and
Cole's answer (shot order 1-2-4-3) and swaps the matching camera
descriptions in the spatial hard lock. Dialogue text untouched.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "jobs" / "ep_units"

BUFFER_LOCK = "本镜没有任何对白，只有环境声；Cole Mercer不在本镜开口，" \
              "不得提前说出他的台词。"

HARDLOCK_OLD = (
    "第三镜机位在 Cole 北侧约一米半，朝南，拍他转向东边 Danny 的左侧面；"
    "第四镜机位在 Danny 西北约一米半，朝东南，拍 Danny 正面，背后是勘测艇船尾。"
)
HARDLOCK_NEW = (
    "第三镜机位在 Danny 西北约一米半，朝东南，拍 Danny 正面，背后是勘测艇船尾；"
    "第四镜机位在 Cole 北侧约一米半，朝南，拍他转向东边 Danny 的左侧面。"
)
FLOW_OLD = (
    "变化与落点：Sienna 低头看浮板，再抬眼看 Cole；Cole 右手从胸口放下，"
    "下巴朝浮板一抬，原地转身面朝东看 Danny，说话，右手掌心朝下在身前往南一送；"
    "Danny 原地，看浮板再看 Cole，犹豫。"
)
FLOW_NEW = (
    "变化与落点：Sienna 低头看浮板，再抬眼看 Cole；Danny 原地，看浮板再看 Cole，"
    "犹豫；Cole 右手从胸口放下，下巴朝浮板一抬，原地转身面朝东看 Danny，说话，"
    "右手掌心朝下在身前往南一送。"
)


def main() -> int:
    src = next(SRC_DIR.glob("EP33-潮缚-fix2-U01"))
    dst = SRC_DIR / "EP33-潮缚-fix3-U01"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    (dst / "assets" / "prompt_audit.json").unlink(missing_ok=True)
    p = dst / "assets" / "prompt_source.txt"
    text = p.read_text(encoding="utf-8")
    for old, new in ((HARDLOCK_OLD, HARDLOCK_NEW), (FLOW_OLD, FLOW_NEW)):
        assert old in text, f"hardlock target not found: {old[:30]}"
        text = text.replace(old, new)
    print("hardlock: camera order + flow swapped")

    lines = text.split("\n")
    idx = [i for i, ln in enumerate(lines) if ln.startswith("▲")]
    assert len(idx) == 4, f"expected 4 shots, got {len(idx)}"
    shots = [lines[i] for i in idx]
    # orig order: 0=wide, 1=Sienna, 2=Cole, 3=Danny.
    # new order: wide, Sienna, Danny(buffer), Cole.
    shots[3] = shots[3].rstrip() + BUFFER_LOCK
    new_order = [shots[0], shots[1], shots[3], shots[2]]
    for pos, i in enumerate(idx):
        lines[i] = new_order[pos]
    print("shots reordered: wide -> Sienna -> Danny(buffer) -> Cole")
    p.write_text("\n".join(lines), encoding="utf-8")
    print(f"EP33-U01: fix3 built {src.name} -> {dst.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
