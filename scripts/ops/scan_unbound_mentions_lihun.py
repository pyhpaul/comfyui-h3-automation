#!/usr/bin/env python3
"""Scan lihun v23 job prompts for unbound-but-described characters.

Generalized from scan_unbound_mentions.py (which is hard-coded to the
shouming cast): the character roster is built from the jobs themselves
(``Name @char-001-W01［...］`` lines in prompt_source.txt), bound ids
come from job.yaml fields, and any roster character who is named in a
unit's prompt but not bound in that unit is flagged:

  A  named inside 【H3 latent 接入文字】 with visual presence (highest risk)
  B  named only in 不入画/已离开 style declarations

Usage: scan_unbound_mentions_lihun.py [EP01 EP02 ...]   (default: all)
Job glob: jobs/ep_units/<EP>-继母-v23-U*
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GLOB = "*-继母-v23-U*"

_ROSTER = re.compile(r"^(.+?)(?:［[^］]*］)?\s*@char-(\d+)-", re.M)
_OFF = re.compile(r"不入画|不出现|不再入画|已离开|已经离开|已出|出画|画外|不让.*入画|不得让|留在画外")
_SENT_SPLIT = re.compile(r"[^。；\n]*")


def build_roster() -> dict[str, str]:
    roster: dict[str, str] = {}
    for job in sorted((ROOT / "jobs/ep_units").glob(GLOB)):
        src = job / "assets/prompt_source.txt"
        if not src.is_file():
            continue
        for name, cid in _ROSTER.findall(src.read_text(encoding="utf-8")):
            roster.setdefault(f"char-{cid}", name.strip())
    return roster


def sentences_with(text: str, name: str) -> list[str]:
    out = []
    for m in re.finditer(rf"\b{re.escape(name)}\b", text):
        start = max(text.rfind("。", 0, m.start()), text.rfind("；", 0, m.start()),
                    text.rfind("\n", 0, m.start())) + 1
        ends = [i for i in (text.find("。", m.end()), text.find("；", m.end()),
                            text.find("\n", m.end())) if i != -1]
        end = min(ends) + 1 if ends else len(text)
        out.append(text[start:end].strip())
    return out


def main() -> int:
    roster = build_roster()
    print(f"roster: {roster}")
    wanted = [a.upper() for a in sys.argv[1:]]
    flagged = 0
    for job in sorted((ROOT / "jobs/ep_units").glob(GLOB)):
        if wanted and not any(job.name.startswith(w + "-") for w in wanted):
            continue
        raw = yaml.safe_load((job / "job.yaml").read_text(encoding="utf-8"))
        bound = set()
        for v in (raw.get("fields") or {}).values():
            m = re.search(r"(char-\d+)", str(v))
            if m:
                bound.add(m.group(1))
        src = (job / "assets/prompt_source.txt").read_text(encoding="utf-8")
        lat = ""
        m = re.search(r"【H3 latent 接入文字】(.*?)(?=\n【|\Z)", src, re.S)
        if m:
            lat = m.group(1)
        for aid, name in roster.items():
            if aid in bound or not re.search(rf"\b{re.escape(name)}\b", src):
                continue
            a = [s for s in sentences_with(lat, name) if s]
            sents = sentences_with(src, name)
            b = [s for s in sents if _OFF.search(s)]
            if a:
                flagged += 1
                print(f"A {job.name} {name}({aid}) 未绑图却在接入文字里出现:")
                for s in a[:3]:
                    print(f"    {s[:140]}")
            elif b and len(sents) > len(b):
                flagged += 1
                print(f"B {job.name} {name}({aid}) 未绑图、具名提及 x{len(sents)}（含不入画句）:")
                for s in sents[:3]:
                    print(f"    {s[:140]}")
    print(f"flagged={flagged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
