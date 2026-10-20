#!/usr/bin/env python3
"""Build -fix1 copies of Chaofu problem-unit jobs with surgical locks.

Diagnosis basis (2026-10-20, Feiniu 潮缚（10.16） QC annotations + local
ASR/frame check):
- 11 dialogue units: script lines are all spoken correctly (ASR overlap
  >= 0.92); the mismatch is WHO is on screen / mouthing (e.g. EP06-U04 and
  EP53-U05 first shots show the wrong person delivering the line).
- EP50-U02 / EP42-U04 / EP51-U06 / EP41-U05 also repeat a phrase.
- EP24 (all 6): prompt + scene image are night, renders drifted to dusk.

Edits are additive locks only; dialogue, shots and assets stay untouched:
1. Every dialogue shot gets "本镜画面中只有<说话人>入画，其他人物不入画。"
2. Silent close-up reaction shots get "<人物>嘴唇合上、全程不动唇、不发声。"
   when the paragraph does not already lock the lips.
3. All dialogue units get "每句台词只说一遍，不得重复或回读。"
4. EP06-U04 / EP53-U05 first shots get an outfit identity anchor.
5. EP24 units get a deep-night lock in 【氛围与画质】.

Original jobs are not modified. Prints a per-unit edit summary.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "jobs" / "ep_units"

DIALOGUE_UNITS = [
    "EP06-U04", "EP23-U01", "EP23-U05", "EP33-U01", "EP41-U05",
    "EP42-U02", "EP42-U04", "EP43-U05", "EP50-U02", "EP51-U06",
    "EP53-U05", "EP24-U01", "EP24-U02",
]
EP24_UNITS = [f"EP24-U0{i}" for i in range(1, 7)]
FIRST_SHOT_ANCHOR = {"EP06-U04", "EP53-U05"}
REPEAT_LOCK = "每句台词只说一遍，不得重复或回读。"
NIGHT_LOCK = (
    "现在是深夜：天空与海面全黑，没有黄昏余光，也没有蓝灰色天光；"
    "唯一光源是门廊灯的暖光，人物面部只由这盏灯单侧照亮。"
)


def people_of(text: str) -> list[str]:
    m = re.search(r"人物：([^\n]+)", text)
    if not m:
        return []
    names = []
    for part in re.split(r"[、，]", m.group(1)):
        name = re.sub(r"［[^］]*］", "", part).strip()
        if name and re.search(r"[A-Za-z]", name):
            names.append(name)
    return names


def outfit_of(text: str, name: str) -> str:
    """First 穿着 clause for a character in 【参考设定】, shortened."""
    idx = text.find(name)
    if idx < 0:
        return ""
    seg = text[idx:idx + 600]
    m = re.search(r"穿着([^。；]+)", seg)
    if not m:
        return ""
    clause = m.group(1).split("，")[0].strip()
    return clause


def patch_dialogue(text: str, unit: str, edits: list[str]) -> str:
    people = people_of(text)
    if not people:
        edits.append("!! no people parsed")
        return text

    # global repeat lock, right after the no-narration rule
    anchor = "不得插入旁白。"
    if anchor in text and REPEAT_LOCK not in text:
        text = text.replace(anchor, anchor + REPEAT_LOCK, 1)
        edits.append("repeat-lock")

    paragraphs = text.split("\n")
    out_lines: list[str] = []
    shot_no = 0
    for line in paragraphs:
        if not line.startswith("▲"):
            out_lines.append(line)
            continue
        shot_no += 1
        new = line
        if "口型同步开口" in line:
            speaker = next(
                (p for p in people if f"{p}口型同步开口" in line
                 or f"{p}的口型同步开口" in line),
                None,
            )
            if speaker is None:
                speaker = next(
                    (p for p in people
                     if re.search(re.escape(p) + r"[^。]*口型同步开口", line)),
                    None,
                )
            if speaker and "只有" not in line:
                new = line.rstrip() + f"本镜画面中只有{speaker}入画，其他人物不入画。"
                edits.append(f"shot{shot_no}: only-{speaker}")
                if unit in FIRST_SHOT_ANCHOR and shot_no == 1:
                    outfit = outfit_of(text, speaker)
                    others = "、".join(p for p in people if p != speaker)
                    if outfit:
                        new += (
                            f"入画者是{speaker}（穿{outfit}），"
                            f"不是{others}，不得把{speaker}的脸画成{others}。"
                        )
                        edits.append(f"shot1: identity-anchor {speaker}")
            elif speaker is None:
                edits.append(f"shot{shot_no}: !! speaker not parsed")
        elif "近景" in line and "正面" in line:
            bracket = re.search(r"［([^，］]+?)(?:正面|侧面)", line)
            person = None
            if bracket:
                person = next(
                    (p for p in people if bracket.group(1).strip().startswith(p)
                     or p.startswith(bracket.group(1).strip())),
                    None,
                )
            if person is None:
                person = next((p for p in people if p in line), None)
            if person and "不动唇" not in line:
                new = line.rstrip() + f"{person}嘴唇合上、全程不动唇、不发声。"
                edits.append(f"shot{shot_no}: lips-lock {person}")
        out_lines.append(new)
    return "\n".join(out_lines)


def patch_ep24_night(text: str, edits: list[str]) -> str:
    if NIGHT_LOCK in text:
        return text
    # append at the end of the 【氛围与画质】 paragraph
    m = re.search(r"(【氛围与画质】[^\n]*)", text)
    if not m:
        edits.append("!! no 氛围 paragraph")
        return text
    text = text.replace(m.group(1), m.group(1).rstrip() + NIGHT_LOCK, 1)
    edits.append("night-lock")
    return text


def main() -> int:
    units = sorted(set(DIALOGUE_UNITS) | set(EP24_UNITS))
    for unit in units:
        ep, uu = unit.split("-")
        src = next(SRC_ROOT.glob(f"{ep}-潮缚-v1-{uu}"))
        dst = SRC_ROOT / f"{ep}-潮缚-fix1-{uu}"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        # stale audit from the source build must not masquerade as fresh
        (dst / "assets" / "prompt_audit.json").unlink(missing_ok=True)
        p = dst / "assets" / "prompt_source.txt"
        text = p.read_text(encoding="utf-8")
        edits: list[str] = []
        if unit in DIALOGUE_UNITS:
            text = patch_dialogue(text, unit, edits)
        if unit in EP24_UNITS:
            text = patch_ep24_night(text, edits)
        p.write_text(text, encoding="utf-8")
        print(f"{unit}: {'; '.join(edits)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
