"""Redo EP62/EP63 dialogue locks with a safer speaker rule.

make_chaofu_fix1_jobs.patch_dialogue guesses the speaker as the last
person named before 口型同步开口 in the same sentence, which misfires
when the description mentions the listener first (e.g. "眼睛在挡风窗和
Victor Harlow之间来回看，口型同步开口" is Wade speaking). This script
strips every lock that patch just appended to the 62/63 jobs, then
re-appends using: speaker = first person named in the shot body before
the dialogue. Every decision is printed for manual review.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOBS = ROOT / "jobs" / "ep_units"
REPEAT_LOCK = "每句台词只说一遍，不得重复或回读。"

STRIP_RES = [
    re.compile(r"本镜画面中只有[^。]*。"),
    re.compile(r"[^。]*嘴唇合上、全程不动唇、不发声。"),
]


def load_fix1():
    spec = importlib.util.spec_from_file_location(
        "fix1", ROOT / "scripts" / "make_chaofu_fix1_jobs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def first_person(segment: str, people: list[str]) -> str | None:
    best, best_at = None, len(segment) + 1
    for p in people:
        at = segment.find(p)
        if 0 <= at < best_at:
            best, best_at = p, at
    return best


def main() -> int:
    fix1 = load_fix1()
    for ep, count in (("EP62", 7), ("EP63", 6)):
        for i in range(1, count + 1):
            d = JOBS / f"{ep}-潮缚-v2-U0{i}"
            p = d / "assets" / "prompt_source.txt"
            text = p.read_text(encoding="utf-8")
            for rx in STRIP_RES:
                text = rx.sub("", text)
            if REPEAT_LOCK not in text:
                anchor = "禁止读旁白。"
                assert anchor in text, d
                text = text.replace(anchor, anchor + REPEAT_LOCK, 1)
            people = fix1.people_of(text)
            out = []
            shot = 0
            for line in text.split("\n"):
                if not line.startswith("▲"):
                    out.append(line)
                    continue
                shot += 1
                body = line.split("］", 1)[-1]
                if "口型同步开口" in line:
                    seg = body.split("口型同步开口")[0]
                    bracket = re.search(r"［([^］]*)］", line)
                    named = [q for q in people
                             if bracket and q in bracket.group(1)]
                    if len(named) == 1:
                        sp = named[0]
                    else:
                        clauses = [c for c in re.split(r"[，。]", seg)
                                   if any(q in c for q in people)]
                        sp = first_person(clauses[-1], people) if clauses \
                            else first_person(seg, people)
                    assert sp, (d, shot, line)
                    line = line.rstrip() + f"本镜画面中只有{sp}入画，其他人物不入画。"
                    print(f"{ep}-U0{i} shot{shot}: speak {sp}")
                elif "近景" in line and "正面" in line:
                    bracket = re.search(r"［([^，］]+?)(?:正面|侧面)", line)
                    person = None
                    if bracket:
                        person = next(
                            (q for q in people
                             if bracket.group(1).strip().startswith(q)
                             or q.startswith(bracket.group(1).strip())), None)
                    if person is None:
                        person = first_person(body, people)
                    if person:
                        line = line.rstrip() + f"{person}嘴唇合上、全程不动唇、不发声。"
                        print(f"{ep}-U0{i} shot{shot}: lips-lock {person}")
                out.append(line)
            p.write_text("\n".join(out), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
