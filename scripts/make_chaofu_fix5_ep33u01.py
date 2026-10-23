#!/usr/bin/env python3
"""Build EP33-U01 -fix5: Sienna's question becomes off-screen voice.

Six renders fail identically: whenever Sienna gets her own close-up,
the model stretches it and has her speak Cole's answer in her voice
(F0 ~205-219 Hz), then Cole repeats it. Duration anchors and silent
buffer shots did not stop it. Fix5 removes her speaking shot: her
question plays as off-screen voice over Cole's shot (he listens,
mouth still, then answers). Words, speakers and order unchanged;
shot count 4 -> 3, hard-lock cameras renumbered to match.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "jobs" / "ep_units"

NEW_SHOT2 = (
    "▲固定镜头，中景［Cole Mercer侧面，转向东边的Danny］。"
    "画外传来Sienna Harlow的问话：（ What are you trying now? ） "
    "Cole Mercer听着，嘴唇全程不动、不发声；问话结束，他把按在胸口的右手放下来，"
    "下巴朝浮板一抬，转头看向Danny，停一拍才口型同步开口，音量适中、语速平稳、"
    "语气轻描淡写地说：（ Something simple. Danny, push that float board in. "
    "No shove. Just let it drift. ） Cole Mercer说完，右手掌心朝下，"
    "在身前轻轻往外一送，示意他放手就行。本镜画面中只有Cole Mercer入画，"
    "其他人物不入画。这句台词全片只在本镜说这一次，前面没有任何人说过它；"
    "说完合上嘴唇，保持沉默，直到本镜结束。（本镜约六秒）"
)

HARDLOCK_OLD = (
    "第二镜机位在 Cole 东侧约半米、肩高，朝西北，拍 Sienna 正面；"
    "第三镜机位在 Danny 西北约一米半，朝东南，拍 Danny 正面，背后是勘测艇船尾；"
    "第四镜机位在 Cole 北侧约一米半，朝南，拍他转向东边 Danny 的左侧面。"
)
HARDLOCK_NEW = (
    "第二镜机位在 Cole 北侧约一米半，朝南，拍他转向东边 Danny 的左侧面，"
    "Sienna 只以画外声音出现、不入画；"
    "第三镜机位在 Danny 西北约一米半，朝东南，拍 Danny 正面，背后是勘测艇船尾。"
)
FLOW_OLD = (
    "变化与落点：Sienna 低头看浮板，再抬眼看 Cole；Danny 原地，看浮板再看 Cole，"
    "犹豫；Cole 右手从胸口放下，下巴朝浮板一抬，原地转身面朝东看 Danny，说话，"
    "右手掌心朝下在身前往南一送。"
)
FLOW_NEW = (
    "变化与落点：Sienna 在画外发问；Cole 听完，右手从胸口放下，下巴朝浮板一抬，"
    "原地转身面朝东看 Danny，说话，右手掌心朝下在身前往南一送；"
    "Danny 原地，看浮板再看 Cole，犹豫。"
)


def main() -> int:
    src = next(SRC_DIR.glob("EP33-潮缚-fix4-U01"))
    dst = SRC_DIR / "EP33-潮缚-fix5-U01"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    (dst / "assets" / "prompt_audit.json").unlink(missing_ok=True)
    p = dst / "assets" / "prompt_source.txt"
    text = p.read_text(encoding="utf-8")
    for old, new in ((HARDLOCK_OLD, HARDLOCK_NEW), (FLOW_OLD, FLOW_NEW)):
        assert old in text, f"hardlock target not found: {old[:30]}"
        text = text.replace(old, new)
    print("hardlock: cameras renumbered, Sienna off-screen")

    lines = text.split("\n")
    idx = [i for i, ln in enumerate(lines) if ln.startswith("▲")]
    assert len(idx) == 4, f"expected 4 shots, got {len(idx)}"
    # fix4 order: wide, Sienna, Danny, Cole -> fix5: wide, Cole(merged), Danny
    lines[idx[1]] = NEW_SHOT2
    del lines[idx[3]]
    print("shots: Sienna CU removed, question merged into Cole shot as V.O.")
    p.write_text("\n".join(lines), encoding="utf-8")
    print(f"EP33-U01: fix5 built {src.name} -> {dst.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
