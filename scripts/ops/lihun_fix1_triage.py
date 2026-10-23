#!/usr/bin/env python3
"""Triage lihun fix1 candidate_audit.json files (screening only).

Ranks C1–C3 by expected-line coverage and head/tail extras. Never writes
registry verdicts.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / ".cache" / "lihun_v23_fix1_review"


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).split()


def coverage(expected: list[str], segments: list[dict]) -> dict:
    heard = " ".join(s.get("text") or "" for s in segments)
    hw = set(norm(heard))
    missing = []
    hit = 0
    for line in expected:
        lw = norm(line)
        if not lw:
            continue
        ok = sum(1 for w in lw if w in hw) / max(1, len(lw))
        if ok >= 0.7:
            hit += 1
        else:
            missing.append(line)
    # crude extra: words before first expected content
    return {
        "hit": hit,
        "need": len(expected),
        "missing": missing,
        "heard": heard[:200],
        "n_segs": len(segments),
        "t0": segments[0]["start"] if segments else None,
        "t1": segments[-1]["end"] if segments else None,
    }


def main() -> int:
    rows = []
    for audit in sorted(REVIEW.glob("*/*/candidate_audit.json")):
        unit = audit.parent.parent.name
        tag = audit.parent.name
        d = json.loads(audit.read_text(encoding="utf-8"))
        cov = coverage(d.get("expected") or [], d.get("review_segments") or [])
        rows.append((unit, tag, cov, audit.parent))
    by_unit: dict[str, list] = {}
    for unit, tag, cov, path in rows:
        by_unit.setdefault(unit, []).append((tag, cov, path))

    out = ROOT / "runs" / "lihun_v23_fix1_triage.md"
    lines = [
        "# lihun fix1 triage (ASR screening only — NOT verdicts)",
        "",
        f"Audited candidates: {len(rows)} across {len(by_unit)} units",
        "",
    ]
    for unit in sorted(by_unit):
        lines.append(f"## {unit}")
        ranked = sorted(
            by_unit[unit],
            key=lambda x: (-x[1]["hit"], x[1]["t0"] if x[1]["t0"] is not None else 99),
        )
        for tag, cov, path in ranked:
            flag = "COVER" if cov["hit"] == cov["need"] and cov["need"] else "GAP"
            if cov["need"] == 0:
                # no-dialogue unit: any speech is suspicious
                flag = "SILENT_OK" if cov["n_segs"] == 0 or not cov["heard"].strip() else "SPEECH_BAD"
            lines.append(
                f"- **{tag}** `{flag}` hit={cov['hit']}/{cov['need']} "
                f"t={cov['t0']}-{cov['t1']} segs={cov['n_segs']}"
            )
            if cov["missing"]:
                lines.append(f"  - missing: {cov['missing']}")
            if cov["heard"]:
                lines.append(f"  - heard: {cov['heard']!r}")
            lines.append(f"  - path: `{path}`")
        lines.append("")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out} units={len(by_unit)} cands={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
