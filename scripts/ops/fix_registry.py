#!/usr/bin/env python3
"""Candidate registry for fix rounds (see docs/ops/2026-10-21-chaofu-fix-retrospective-and-standard.md).

One JSON file is the single source of truth for a fix round's scoreboard:
which (unit, chain) slots are shipped, which candidates exist, their seeds,
verdicts (strict | relaxed | fail), review evidence and editor cut points.
Never track this in chat memory.

A strict/relaxed verdict is a human decision, not an automated audit
result. It is accepted only with a complete dialogue review record:
method=full-dialogue-watch, scope=all-dialogue-lines, a named reviewer
and concrete evidence. ASR, F0, scene cuts and sparse still frames are
screening evidence and can never justify a passing verdict by themselves.
A later fail returns the slot to pending unless another passing candidate
for the same slot remains.

Usage:
  python scripts/ops/fix_registry.py --registry runs/fixround.json init \
      --units EP06-U04 EP23-U01 --chains orig wenxi
  python scripts/ops/fix_registry.py --registry runs/fixround.json add \
      --unit EP06-U04 --chain orig --tag s2-a1 --seed 40000012 \
      --job-id e865fa5b29fd --mp4 outputs/.../x-audio.mp4
  python scripts/ops/fix_registry.py --registry runs/fixround.json verdict \
      --unit EP06-U04 --chain orig --tag s2-a1 --verdict relaxed \
      --review-method full-dialogue-watch --reviewer lai \
      --review-scope all-dialogue-lines \
      --review-evidence "watched every dialogue segment in motion; ..." \
      --cut "剪掉 4.0s-6.0s 胡话段" --shipped-dir "原工作流/EP06/U04"
  python scripts/ops/fix_registry.py --registry runs/fixround.json status
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path


def load(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"slots": {}, "candidates": []}


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                    encoding="utf-8")


def _empty_review() -> dict:
    return {
        "method": "", "reviewer": "", "scope": "", "evidence": "",
        "reviewed_at": "",
    }


def _refresh_slot(data: dict, unit: str, chain: str) -> None:
    """Derive a slot from candidate verdicts (fail can revoke a pass)."""
    verdicts = [
        c.get("verdict") for c in data.get("candidates", [])
        if c.get("unit") == unit and c.get("chain") == chain
    ]
    key = f"{unit}:{chain}"
    if "strict" in verdicts:
        data["slots"][key] = "shipped-strict"
    elif "relaxed" in verdicts:
        data["slots"][key] = "shipped-relaxed"
    else:
        data["slots"][key] = "pending"


def _validate_pass_review(args: argparse.Namespace) -> None:
    if args.verdict not in ("strict", "relaxed"):
        return
    problems = []
    if args.review_method != "full-dialogue-watch":
        problems.append("--review-method must be full-dialogue-watch")
    if not args.reviewer.strip():
        problems.append("--reviewer is required")
    if args.review_scope != "all-dialogue-lines":
        problems.append("--review-scope must be all-dialogue-lines")
    if len(args.review_evidence.strip()) < 10:
        problems.append("--review-evidence must describe the completed review")
    if problems:
        raise SystemExit(
            "refusing to record a passing verdict without a complete "
            "human dialogue review: " + "; ".join(problems))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", type=Path, required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init")
    p.add_argument("--units", nargs="+", required=True)
    p.add_argument("--chains", nargs="+", default=["orig", "wenxi"])

    p = sub.add_parser("add")
    for a in ("--unit", "--chain", "--tag"):
        p.add_argument(a, required=True)
    for a in ("--seed", "--job-id", "--prompt-id", "--mp4", "--latent"):
        p.add_argument(a, default="")

    p = sub.add_parser("verdict")
    for a in ("--unit", "--chain", "--tag", "--verdict"):
        p.add_argument(a, required=True,
                       help="strict | relaxed | fail" if a == "--verdict" else None)
    p.add_argument("--cut", default="")
    p.add_argument("--shipped-dir", default="")
    p.add_argument("--review-method", default="",
                   help="passing verdicts require full-dialogue-watch")
    p.add_argument("--reviewer", default="")
    p.add_argument("--review-scope", default="",
                   help="passing verdicts require all-dialogue-lines")
    p.add_argument("--review-evidence", default="",
                   help="what was watched and checked, per line")
    p.add_argument("--reviewed-at", default="",
                   help="ISO timestamp; defaults to now (UTC)")

    sub.add_parser("status")
    args = ap.parse_args()
    if args.cmd == "verdict":
        _validate_pass_review(args)
    data = load(args.registry)

    if args.cmd == "init":
        for u in args.units:
            for c in args.chains:
                data["slots"].setdefault(f"{u}:{c}", "pending")
    elif args.cmd == "add":
        data["candidates"].append({
            "unit": args.unit, "chain": args.chain, "tag": args.tag,
            "seed": args.seed, "job_id": args.job_id,
            "prompt_id": args.prompt_id, "mp4": args.mp4,
            "latent": args.latent, "verdict": "", "cut": "",
            "shipped_dir": "", "review": _empty_review()})
    elif args.cmd == "verdict":
        for cand in data["candidates"]:
            if (cand["unit"], cand["chain"], cand["tag"]) == \
                    (args.unit, args.chain, args.tag):
                cand["verdict"] = args.verdict
                cand["cut"] = args.cut
                cand["shipped_dir"] = args.shipped_dir
                cand.setdefault("review", _empty_review())
                if args.verdict in ("strict", "relaxed"):
                    cand["review"] = {
                        "method": args.review_method,
                        "reviewer": args.reviewer.strip(),
                        "scope": args.review_scope,
                        "evidence": args.review_evidence.strip(),
                        "reviewed_at": args.reviewed_at or datetime.now(
                            timezone.utc).isoformat(),
                    }
                break
        else:
            raise SystemExit(f"candidate not found: {args.unit}:{args.chain} {args.tag}")
        _refresh_slot(data, args.unit, args.chain)
    save(args.registry, data)

    if args.cmd in ("init", "status"):
        slots = data["slots"]
        done = sum(1 for v in slots.values() if v.startswith("shipped"))
        print(f"slots shipped: {done}/{len(slots)}")
        for k in sorted(slots):
            print(f"  {k}: {slots[k]}")
    else:
        print(f"{args.cmd} ok -> {args.registry}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
