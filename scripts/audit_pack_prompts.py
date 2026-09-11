#!/usr/bin/env python3
"""Preflight pack-prompt audits for EP unit jobs (disk + simulated parent).

Disk ``prompt_audit.json`` only covers the no-parent build path. Serial U02+
bind ``ref_video_0`` at submit time — this script always exercises that path
unless ``--no-parent-sim`` is set.

Exit 0 only when every selected job passes both gates.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from comfy_orch.paths import project_root
from comfy_orch.prompt_wire import preflight_job_dir


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "jobs",
        nargs="*",
        type=Path,
        help="Job dirs (default: all EP02 causality unit jobs under jobs/ep_units)",
    )
    ap.add_argument(
        "--glob",
        default="EP02-H3-physical-causality-test-v2_1-20260910-U*",
        help="Default glob under jobs/ep_units when no jobs args given",
    )
    ap.add_argument(
        "--no-parent-sim",
        action="store_true",
        help="Skip simulated parent video path (not recommended for serial)",
    )
    ap.add_argument("--json", action="store_true", help="Print full JSON report")
    args = ap.parse_args()

    root = project_root()
    if args.jobs:
        job_dirs = [p.resolve() for p in args.jobs]
    else:
        job_dirs = sorted((root / "jobs" / "ep_units").glob(args.glob))
    if not job_dirs:
        print("no job dirs matched", file=sys.stderr)
        return 2

    reports = []
    failed = 0
    for job_dir in job_dirs:
        rep = preflight_job_dir(job_dir, require_parent_path=not args.no_parent_sim)
        reports.append(rep)
        unit = rep.get("unit_id") or job_dir.name
        status = "PASS" if rep["ok"] else "FAIL"
        warn_n = 0
        for key in ("no_parent", "with_parent"):
            block = rep.get(key) or {}
            warn_n += len(block.get("warnings") or [])
        print(f"{status} {unit} warnings={warn_n}", flush=True)
        if not rep["ok"]:
            failed += 1
            for key in ("no_parent", "with_parent"):
                block = rep.get(key) or {}
                for v in block.get("violations") or []:
                    print(f"  [{key}] {v}", flush=True)
        elif warn_n:
            for key in ("no_parent", "with_parent"):
                block = rep.get(key) or {}
                for w in block.get("warnings") or []:
                    print(f"  warn[{key}] {w}", flush=True)

    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
