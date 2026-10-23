#!/usr/bin/env python3
"""Build EP33-U01 -fix6: question in the wide, answer CU, action tail.

fix5 (question as voice-over on Cole's shot) moved the failure: her
voice continued off-screen into Cole's line (F0 222 Hz), then Cole
repeated it on camera. Fix6:
- shot 1 (wide): Sienna asks from inside the wide shot — no close-up
  mouth to sync, Cole looks down and does not move his lips.
- shot 2 (Cole CU): he only answers.
- shot 3 (Danny): a long silent action beat (walks to the float
  board, reaches for the rope, stops, steps back) fills the tail so
  the model has no dead air to pad with a repeat. End state matches
  the original hand-off (Danny still hesitating, board unpushed).
Dialogue text untouched.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "jobs" / "ep_units"

NEW_SHOT1 = (
    "▲缓慢下摇镜头，全景［栈桥南沿，Cole Mercer脚边的木桩］。"
    "Cole Mercer站在木桩边，目光落到脚边：一块旧浮板被缆绳拴在栈桥南沿的木桩上，"
    "板面泡得发白，随着浪一下一下磕着木桩，发出闷闷的轻响。"
    "Sienna Harlow站在Cole Mercer北侧半米，开口问：（ What are you trying now? ） "
    "Cole Mercer没有抬头，嘴唇不动。本镜是全景，不给任何人近景口型特写。"
)
NEW_SHOT3 = (
    "▲固定镜头，中景［Danny正面，背后是勘测艇］。"
    "Danny看看浮板，又看看Cole Mercer，眉毛皱到一起，慢慢朝浮板走过去，蹲下，"
    "手伸向拴着浮板的缆绳又停住，没有碰，站起来退回原地，站在原地犹豫。"
    "Danny全程嘴唇紧闭、不动唇、不发出任何声音，只有环境声。"
    "本镜没有任何对白。（本镜约五秒）"
)
REPLACES = [
    (
        "画外传来Sienna Harlow的问话：（ What are you trying now? ） "
        "Cole Mercer听着，嘴唇全程不动、不发声；问话结束，他把按在胸口的右手放下来，"
        "下巴朝浮板一抬，转头看向Danny，停一拍才口型同步开口",
        "Cole Mercer把按在胸口的右手放下来，下巴朝浮板一抬，"
        "转头看向Danny，停一拍，口型同步开口",
    ),
    (
        "Sienna 只以画外声音出现、不入画；",
        "Sienna 只在第一镜全景里入画；",
    ),
    (
        "变化与落点：Sienna 在画外发问；Cole 听完，右手从胸口放下，"
        "下巴朝浮板一抬，原地转身面朝东看 Danny，说话，"
        "右手掌心朝下在身前往南一送；Danny 原地，看浮板再看 Cole，犹豫。",
        "变化与落点：Sienna 开口发问，Cole 没有抬头；Cole 随后右手从胸口放下，"
        "下巴朝浮板一抬，原地转身面朝东看 Danny，说话，"
        "右手掌心朝下在身前往南一送；Danny 慢慢走向浮板，蹲下，"
        "手伸向缆绳又停住，站起来退回原地犹豫。",
    ),
]


def main() -> int:
    src = next(SRC_DIR.glob("EP33-潮缚-fix5-U01"))
    dst = SRC_DIR / "EP33-潮缚-fix6-U01"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    (dst / "assets" / "prompt_audit.json").unlink(missing_ok=True)
    p = dst / "assets" / "prompt_source.txt"
    text = p.read_text(encoding="utf-8")
    for old, new in REPLACES:
        assert old in text, f"replace target not found: {old[:36]}"
        text = text.replace(old, new)
        print(f"replaced: {old[:32]}...")
    lines = text.split("\n")
    idx = [i for i, ln in enumerate(lines) if ln.startswith("▲")]
    assert len(idx) == 3, f"expected 3 shots, got {len(idx)}"
    lines[idx[0]] = NEW_SHOT1
    lines[idx[2]] = NEW_SHOT3
    print("shots: wide+question, Cole answer, Danny silent action")
    p.write_text("\n".join(lines), encoding="utf-8")
    print(f"EP33-U01: fix6 built {src.name} -> {dst.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
