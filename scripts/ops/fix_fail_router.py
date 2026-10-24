#!/usr/bin/env python3
"""Route fix-round failures: ban same-prompt ×3 empty retries; classify A/B/C/D/E.

Reads ``fix_registry.json`` + optional edit_plan / failall dispatch notes.

  PYTHONPATH=src python scripts/ops/fix_fail_router.py \
    --registry runs/lihun_v23_fix_registry.json --write runs/lihun_v23_fix_routes.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Heuristic keyword → class (override with --note-map later if needed)
_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("A", re.compile(r"片头|片尾|BAD_extra|胡话黏|剪头|head[- ]?junk", re.I)),
    ("B", re.compile(r"无对白|全程胡话|闭口|silent.?unit|Yeah,\s*wait", re.I)),
    ("C", re.compile(r"缺失|BAD_missing|短问|Whose|低重合|BAD_low", re.I)),
    ("D", re.compile(r"Noah|假通过|人名|Ava|Damian", re.I)),
    ("E", re.compile(r"同念|双人|听者|chorus|lip.?own", re.I)),
]


def _classify(text: str) -> str:
    for code, pat in _RULES:
        if pat.search(text or ""):
            return code
    return "D"  # unknown → treat as needs human/structure, not blind seed


def _attempts_by_unit(candidates: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for c in candidates:
        out[c.get("unit", "")].append(c)
    return out


def route_registry(data: dict, notes: dict[str, str] | None = None) -> dict:
    notes = notes or {}
    by_unit = _attempts_by_unit(data.get("candidates") or [])
    routes = []
    for unit, cands in sorted(by_unit.items()):
        fails = [c for c in cands if c.get("verdict") == "fail"]
        passes = [c for c in cands if c.get("verdict") in ("strict", "relaxed")]
        if passes or not fails:
            continue
        note = notes.get(unit, "")
        # gather evidence strings
        blob = " ".join(
            [
                note,
                *[str(c.get("cut") or "") for c in fails],
                *[str((c.get("review") or {}).get("evidence") or "") for c in fails],
            ]
        )
        cls = _classify(blob or unit)
        n_fail = len(fails)
        ban_same_prompt_retry = n_fail >= 3 and cls in {"A", "B", "E"}
        if cls == "A":
            action = "prefer_relaxed_cut_no_rerender"
            max_new_seeds = 0
        elif cls == "B":
            action = "prompt_closed_mouth_lock_then_seed_batch"
            max_new_seeds = 6
        elif cls == "C":
            action = "restructure_or_duration_then_seed_batch"
            max_new_seeds = 6
        elif cls == "E":
            action = "listener_closed_lock_then_seed_batch"
            max_new_seeds = 6
        else:
            action = "name_enunciate_or_frame_review"
            max_new_seeds = 2
        routes.append(
            {
                "unit": unit,
                "class": cls,
                "fail_attempts": n_fail,
                "ban_same_prompt_x3": ban_same_prompt_retry or n_fail >= 3,
                "action": action,
                "max_new_seeds_after_fix": max_new_seeds,
                "note": note[:200],
            }
        )
    return {
        "schema": "fix-fail-routes/v1",
        "policy": (
            "Never open another same-prompt ×3 seed wave without structural change. "
            "Class A → cut; B/E → mouth locks; C → duration/structure; then one 4–6 seed batch."
        ),
        "routes": routes,
    }


def _notes_from_edit_plan(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for m in re.finditer(r"^\| (EP\d+) \|.*?\| (.*?) \|.*?\|$", text, re.M):
        ep, qc = m.group(1), m.group(2)
        for um in re.finditer(r"(U\d+)", qc):
            out[f"{ep}-{um.group(1)}"] = qc
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--registry", type=Path, required=True)
    ap.add_argument("--edit-plan", type=Path, default=ROOT / "runs/lihun_v23_edit_plan.md")
    ap.add_argument("--write", type=Path, help="Write routes JSON")
    args = ap.parse_args()
    data = json.loads(args.registry.read_text(encoding="utf-8"))
    notes = _notes_from_edit_plan(args.edit_plan)
    report = route_registry(data, notes)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(text, encoding="utf-8")
        print(f"wrote {args.write} routes={len(report['routes'])}", flush=True)
    else:
        print(text)
    banned = sum(1 for r in report["routes"] if r["ban_same_prompt_x3"])
    print(f"SUMMARY routes={len(report['routes'])} ban_same_prompt_x3={banned}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
