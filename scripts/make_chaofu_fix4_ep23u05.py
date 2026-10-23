#!/usr/bin/env python3
"""Build EP23-U05 -fix4: write out the hard lock's silent shots 2/3.

The pack's shot block has only Cole's speaking close-up, while the
spatial hard lock describes three cameras (Cole CU -> tilt up to the
porch lamp -> two-shot side view). fix2/fix3 appends even told the
model not to cut, contradicting the hard lock; renders improvised
the missing shots and filled them with Wade's invented mumbled
speech. Fix4 starts from fix1, keeps Cole's shot, and writes shots
2/3 explicitly as silent (lamp insert with no people; Wade steps in,
lips sealed, silent two-shot). The tail-freeze block is reworded to
match the three-shot structure. Dialogue text untouched.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "jobs" / "ep_units"

SHOT2 = (
    "▲缓慢上摇镜头［台阶下的院子里仰拍，从台阶缓缓上摇到入户门上方的门廊灯］。"
    "画面里只有忽明忽暗的门廊灯和绕着灯罩撞的飞虫，没有人物入画，"
    "没有任何对白，只有海风声和灯的细微电流声。"
)
SHOT3 = (
    "▲固定镜头，中景［门廊东侧朝西，拍两人侧面］。"
    "Wade Mercer放下右手，向西偏北迈一大步，站到Cole Mercer北偏东约一米、"
    "入户门正南约一米，身体转向南偏西对着Cole Mercer，双手垂下，肩膀放低；"
    "Cole Mercer身体随着他转向北偏东，看着他。两人沉默对视，"
    "Wade Mercer嘴唇动了一下随即紧紧闭上，全程不发声、不开口；"
    "Cole Mercer也不开口。本镜没有任何对白，只有海风声。"
)
REPLACES = [
    (
        "嘴唇动了动；Cole 身体随着他转向北偏东。",
        "嘴唇动了一下随即紧闭、不出声；Cole 身体随着他转向北偏东。",
    ),
    (
        "【片尾硬锁】对白镜头是本条最后一镜：说完后立即定格闭嘴，"
        "禁止后续切镜、禁止任何口型与语音，音频轨对白结束后绝对静音。",
        "【片尾硬锁】对白只出现在第一镜：Cole Mercer说完立即闭嘴；"
        "第二、三镜全程没有任何口型与语音，禁止喃喃低语和含混假台词，"
        "音频轨对白结束后只有环境声。",
    ),
]


def main() -> int:
    src = next(SRC_DIR.glob("EP23-潮缚-fix1-U05"))
    dst = SRC_DIR / "EP23-潮缚-fix4-U05"
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
    assert len(idx) == 1, f"expected 1 shot in fix1, got {len(idx)}"
    lines[idx[0]] = lines[idx[0]].rstrip() + "说完立刻合上嘴唇，保持沉默。"
    lines.insert(idx[0] + 1, SHOT2)
    lines.insert(idx[0] + 2, SHOT3)
    print("shots: Cole line + silent lamp insert + silent two-shot")
    p.write_text("\n".join(lines), encoding="utf-8")
    print(f"EP23-U05: fix4 built {src.name} -> {dst.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
