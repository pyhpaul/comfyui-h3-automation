#!/usr/bin/env python3
"""Candidate registry for fix rounds (see docs/ops/2026-10-21-chaofu-fix-retrospective-and-standard.md).

One JSON file is the single source of truth for a fix round's scoreboard:
which (unit, chain) slots are shipped, which candidates exist, their seeds,
verdicts (strict | relaxed | fail) and editor cut points. Never track this
in chat memory.

Usage:
  python scripts/ops/fix_registry.py --registry runs/fixround.json init \
      --units EP06-U04 EP23-U01 --chains orig wenxi
  python scripts/ops/fix_registry.py --registry runs/fixround.json add \
      --unit EP06-U04 --chain orig --tag s2-a1 --seed 40000012 \
      --job-id e865fa5b29fd --mp4 outputs/.../x-audio.mp4
  python scripts/ops/fix_registry.py --registry runs/fixround.json verdict \
      --unit EP06-U04 --chain orig --tag s2-a1 --verdict relaxed \
      --cut "剪掉 4.0s-6.0s 胡话段" --shipped-dir "原工作流/EP06/U04"
  python scripts/ops/fix_registry.py --registry runs/fixround.json status
"""
from __future__ import annotations

import argparse
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

    sub.add_parser("status")
    args = ap.parse_args()
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
            "shipped_dir": ""})
    elif args.cmd == "verdict":
        for cand in data["candidates"]:
            if (cand["unit"], cand["chain"], cand["tag"]) == \
                    (args.unit, args.chain, args.tag):
                cand["verdict"] = args.verdict
                cand["cut"] = args.cut
                cand["shipped_dir"] = args.shipped_dir
                break
        else:
            raise SystemExit(f"candidate not found: {args.unit}:{args.chain} {args.tag}")
        if args.verdict in ("strict", "relaxed"):
            data["slots"][f"{args.unit}:{args.chain}"] = \
                f"shipped-{args.verdict}"
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
