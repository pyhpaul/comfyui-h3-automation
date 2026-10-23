#!/usr/bin/env python3
"""Scan H3 job prompts for unbound-but-described characters.

Lesson from EP01-U05 (寿命掮客): the latent-access text described a
character leaning on the hero's arm while the same unit declared her
off-frame in three other places and bound no reference image for her.
The model drew an unanchored woman. audit_pack_prompts.py checks wiring
only and cannot see this.

Flags, per unit:
  A  character NOT bound as ref_image but described with visual
     presence inside 【H3 latent 接入文字】 (highest risk)
  B  character NOT bound but named in a 不入画/已离开 style declaration
     (repeated naming + negative instruction still cues the model)

Usage: scan_unbound_mentions.py EP02 EP03   (default: EP01..EP06)
Job glob: jobs/ep_units/<EP>-寿命掮客-v1-U*
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

CHAR_NAMES = {
    "char-001": "Kai Mercer",
    "char-002": "Preston Hale",
    "char-003": "Brooke Lane",
    "char-004": "June Park",
    "char-005": "Sloane Ashford",
    "char-006": "Grant Ashford",
    "char-007": "Leland Ashford",
}
_OFF = re.compile(r"不入画|不出现|不再入画|已离开|已经离开|已出|出画|退回.*后|不让.*入画|不得让")
_SENT = re.compile(r"[^。；\n]*")


def sentences_with(text: str, name: str) -> list[str]:
    out = []
    for m in re.finditer(re.escape(name), text):
        start = max(text.rfind("。", 0, m.start()), text.rfind("；", 0, m.start()),
                    text.rfind("\n", 0, m.start())) + 1
        ends = [i for i in (text.find("。", m.end()), text.find("；", m.end()),
                            text.find("\n", m.end())) if i != -1]
        end = min(ends) + 1 if ends else len(text)
        out.append(text[start:end].strip())
    return out


def main() -> int:
    eps = [a.upper() for a in sys.argv[1:]] or [f"EP{e:02d}" for e in range(1, 7)]
    flagged = 0
    for ep in eps:
        for job in sorted((ROOT / "jobs/ep_units").glob(f"{ep}-寿命掮客-v1-U*")):
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
            for aid, name in CHAR_NAMES.items():
                if aid in bound or name not in src:
                    continue
                sents = sentences_with(src, name)
                a = [s for s in sentences_with(lat, name) if s]
                b = [s for s in sents if _OFF.search(s)]
                if a:
                    flagged += 1
                    print(f"A {job.name} {name} 未绑图却在接入文字里有画面描述:")
                    for s in a:
                        print(f"    {s[:140]}")
                elif b:
                    flagged += 1
                    print(f"B {job.name} {name} 未绑图、仅以「不入画」类句被提及 x{len(sents)}:")
                    for s in sents[:4]:
                        print(f"    {s[:140]}")
    print(f"flagged={flagged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
