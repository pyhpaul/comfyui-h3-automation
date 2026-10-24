#!/usr/bin/env python3
"""Print lihun fix1 registry + edit-readiness snapshot for 5m loop reports."""
from __future__ import annotations
import json, re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REG = ROOT / "runs/lihun_v23_fix_registry.json"
EDIT = ROOT / "runs/lihun_v23_edit_plan.md"

def main() -> int:
    reg = json.loads(REG.read_text(encoding="utf-8"))
    slots = reg["slots"]
    st = Counter(slots.values())
    shipped = sum(1 for v in slots.values() if str(v).startswith("shipped"))
    by_ep: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for k, v in slots.items():
        u = k.split(":")[0]
        by_ep[u.split("-")[0]].append((u, str(v)))
    by_u: dict[str, list[str]] = defaultdict(list)
    for c in reg["candidates"]:
        by_u[c["unit"]].append(c.get("verdict") or "unset")
    failall = sorted(u for u, vs in by_u.items() if vs and all(x == "fail" for x in vs))
    unset = sorted(u for u, vs in by_u.items() if any(x == "unset" for x in vs))
    ready = []
    for ep, items in sorted(by_ep.items(), key=lambda x: int(x[0][2:])):
        if items and all(s.startswith("shipped") for _, s in items):
            ready.append(ep)
    edit_txt = EDIT.read_text(encoding="utf-8") if EDIT.exists() else ""
    waiting = re.findall(r"\|\s*(EP\d+)\s*\|[^|]*\|[^|]*\|\s*等[^|]*\|", edit_txt)
    print(f"FIX1 slots shipped={shipped}/{len(slots)} {dict(st)}")
    print(f"FIX1 units unset_tags={len(unset)} failall={len(failall)}")
    if unset[:12]:
        print("  unset:", ", ".join(unset[:12]) + ("…" if len(unset) > 12 else ""))
    if failall:
        print("  failall:", ", ".join(failall))
    print(f"EDIT-ready EPs (all fix slots shipped): {', '.join(ready) or '(none)'}")
    still_wait = [ep for ep in waiting if ep in ready]
    print(f"EDIT-ready but edit_plan still 等重做: {', '.join(still_wait) or '(none)'}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
