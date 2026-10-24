#!/usr/bin/env python3
"""Post-archive unit QC orchestration: parallel L1 dialogue-check + L0 risk plan.

Does **not** remake. Writes ``runs/visual_qc/<batch_slug>/`` for
``comfy-h3-unit-visual-qc`` and optional dialogue-check report.

  PYTHONPATH=src python scripts/ops/post_feiniu_unit_qc.py \
    --batch '离婚后（10.22）' --episode EP01 \
    --job-root jobs/ep_units --job-glob 'EP01-*U*' \
    --video-root /path/to/mp4s   # optional; enables L1

Uses local CPU/GPU only — never the rented Comfy card.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from comfy_orch.pack_render_risk import high_risk_codes, scan_render_risks  # noqa: E402

_UNIT_RE = re.compile(r"(EP\d+).*?(U\d+)", re.I)


def _slug(batch: str) -> str:
    return re.sub(r"[^\w\-]+", "_", batch).strip("_")[:80]


def _unit_id(job_dir: Path) -> str | None:
    m = _UNIT_RE.search(job_dir.name)
    if not m:
        return None
    return f"{m.group(1).upper()}-{m.group(2).upper()}"


def scan_l0(job_dirs: list[Path]) -> list[dict]:
    rows = []
    for job in job_dirs:
        uid = _unit_id(job)
        src = job / "assets" / "prompt_source.txt"
        if not uid or not src.is_file():
            continue
        text = src.read_text(encoding="utf-8")
        risks = scan_render_risks(text)
        high = high_risk_codes(risks)
        chorus = "E" in high
        rows.append(
            {
                "unit": uid,
                "job_dir": str(job.relative_to(ROOT)) if job.is_relative_to(ROOT) else str(job),
                "L0_unit_risk": "HIGH" if chorus or "B" in high else ("MED" if risks else "LOW"),
                "L0_codes": [r.code for r in risks],
                "L0_messages": [r.message for r in risks],
                "L2_required": bool(chorus),
                "prompt_path": str((job / "assets" / "prompt_source.txt").relative_to(ROOT))
                if job.is_relative_to(ROOT)
                else str(src),
            }
        )
    return rows


def run_l1(video_root: Path, job_root: Path, report: Path, prefixes: list[str]) -> dict:
    cmd = [
        sys.executable,
        str(ROOT / "scripts/ops/batch_dialogue_check.py"),
        "--video-root",
        str(video_root),
        "--job-root",
        str(job_root),
        "--report",
        str(report),
    ]
    for p in prefixes:
        cmd.extend(["--prefix", p])
    try:
        subprocess.check_call(cmd, cwd=str(ROOT), env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "PYTHONPATH": "src"})
        return {"ok": True, "report": str(report)}
    except subprocess.CalledProcessError as exc:
        return {"ok": False, "error": str(exc), "report": str(report)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch", required=True)
    ap.add_argument("--episode", required=True, help="EPxx")
    ap.add_argument("--job-root", type=Path, default=ROOT / "jobs/ep_units")
    ap.add_argument("--job-glob", default="", help="default: {episode}-*U*")
    ap.add_argument("--video-root", type=Path, help="mp4 root for L1; omit to skip ASR")
    ap.add_argument("--prefix", action="append", default=[], help="EP=jobPrefix for L1")
    args = ap.parse_args()

    glob_pat = args.job_glob or f"{args.episode}-*U*"
    job_dirs = sorted(args.job_root.glob(glob_pat))
    if not job_dirs:
        print(f"no jobs for {glob_pat}", file=sys.stderr)
        return 2

    out_dir = ROOT / "runs" / "visual_qc" / _slug(args.batch) / args.episode
    out_dir.mkdir(parents=True, exist_ok=True)

    l1_report = out_dir / "dialogue_check.json"
    l0_rows: list[dict] = []
    l1_info: dict = {"ok": None, "skipped": True}

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_l0 = pool.submit(scan_l0, job_dirs)
        fut_l1 = None
        if args.video_root:
            prefixes = args.prefix or [f"{args.episode}={args.episode}"]
            fut_l1 = pool.submit(
                run_l1, args.video_root.resolve(), args.job_root.resolve(), l1_report, prefixes
            )
        l0_rows = fut_l0.result()
        if fut_l1 is not None:
            l1_info = fut_l1.result()
            l1_info["skipped"] = False

    high = [r for r in l0_rows if r["L0_unit_risk"] == "HIGH"]
    plan = {
        "schema": "visual_qc_plan/v1",
        "batch": args.batch,
        "episode": args.episode,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "policy": (
            "Parallel L0 prompt risk + optional L1 ASR. "
            "L2 full watch only for L2_required / human escalate. "
            "Do not auto-remake; route fails via fix_fail_router."
        ),
        "L1": l1_info,
        "units": l0_rows,
        "human_spot_check": {
            "priority": "dual-shot chorus first",
            "suggested_units": [r["unit"] for r in high][:5],
            "per_episode_cap": 2,
        },
    }
    plan_path = out_dir / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = [
        f"# Visual QC plan {args.episode} / {args.batch}",
        "",
        f"- Units: {len(l0_rows)}; HIGH: {len(high)}",
        f"- L1: {l1_info}",
        f"- Next: run `comfy-h3-unit-visual-qc` on HIGH / L2_required only",
        "",
        "| unit | L0 | codes | L2_required |",
        "|---|---|---|---|",
    ]
    for r in l0_rows:
        md.append(
            f"| {r['unit']} | {r['L0_unit_risk']} | {','.join(r['L0_codes']) or '-'} | "
            f"{r['L2_required']} |"
        )
    (out_dir / "plan.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "out": str(out_dir.relative_to(ROOT)),
                "units": len(l0_rows),
                "high": len(high),
                "l1": l1_info.get("ok"),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0 if l1_info.get("ok", True) is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
