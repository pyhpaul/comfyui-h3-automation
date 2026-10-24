#!/usr/bin/env python3
"""Set job.yaml duration_seconds from English （） dialogue estimate + pad.

Run after unpack / before queue to cut head-tail filler (fail class A/DURATION).

  PYTHONPATH=src python scripts/ops/apply_dialogue_duration.py jobs/ep_units/EP01-*-U*
  PYTHONPATH=src python scripts/ops/apply_dialogue_duration.py jobs/... --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from comfy_orch.pack_render_risk import (  # noqa: E402
    estimate_dialogue_duration_s,
    extract_en_dialogue_lines,
)


def patch_job(job_dir: Path, *, pad_s: float, dry_run: bool) -> dict:
    job_path = job_dir / "job.yaml"
    src = job_dir / "assets" / "prompt_source.txt"
    if not job_path.is_file() or not src.is_file():
        raise FileNotFoundError(job_dir)
    prompt = src.read_text(encoding="utf-8")
    lines = extract_en_dialogue_lines(prompt)
    raw = yaml.safe_load(job_path.read_text(encoding="utf-8")) or {}
    fields = raw.setdefault("fields", {})
    old = float(fields.get("duration_seconds") or 0) or None
    if not lines:
        return {
            "job": str(job_dir),
            "skipped": "no_en_dialogue",
            "old": old,
        }
    new = estimate_dialogue_duration_s(prompt, pad_s=pad_s)
    # H3 UI often uses xxx.083 endings; keep one decimal+.083 style if old had it
    if old and abs(old - int(old) - 0.083) < 1e-6:
        new = round(new) + 0.083
    else:
        new = round(new, 3)
    out = {"job": str(job_dir), "old": old, "new": new, "lines": len(lines)}
    if dry_run or (old is not None and abs(old - new) < 0.05):
        out["changed"] = False
        return out
    fields["duration_seconds"] = new
    job_path.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    out["changed"] = True
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("jobs", nargs="+", type=Path)
    ap.add_argument("--pad-s", type=float, default=2.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    n_change = 0
    for job in args.jobs:
        job = job.resolve()
        if not job.is_dir():
            print(f"SKIP not_dir {job}", flush=True)
            continue
        info = patch_job(job, pad_s=args.pad_s, dry_run=args.dry_run)
        if info.get("changed"):
            n_change += 1
        print(info, flush=True)
    print(f"DONE changed={n_change}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
