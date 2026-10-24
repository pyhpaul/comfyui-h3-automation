#!/usr/bin/env python3
"""As each local pilot seed lands, run dialogue QC + audit_candidate (CPU).

Does not touch the rented Comfy GPU. Vision L2 still needs the visual-qc
skill on HIGH / dual-shot units; this sidecar writes a rolling plan + L1.

L3 blooper triage is opt-in (``--l3``): use for winners / when a batch looks
heavily broken — not every seed. L3 ranks human-scan priority; not a clear bill.

  PYTHONPATH=src python scripts/ops/watch_pilot_qc_sidecar.py \
    --out-dir .cache/lihun_v23_pilot_abcd_1024 \
    --expect 14
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from comfy_orch.dialogue_gate import (  # noqa: E402
    extract_expected_dialogue,
    mp4_to_wav,
    score_transcript,
    transcribe_wav_faster_whisper,
)
from comfy_orch.pack_render_risk import high_risk_codes, scan_render_risks  # noqa: E402

_UNIT_RE = re.compile(r"(EP\d+)-U(\d+)", re.I)
_JOB = {
    "EP11-U04": ROOT / "jobs/ep_units/EP11-继母-v23-U04",
    "EP43-U06": ROOT / "jobs/ep_units/EP43-继母-v23-U06",
    "EP19-U06": ROOT / "jobs/ep_units/EP19-继母-v23-U06",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def find_mp4(cand: Path) -> Path | None:
    mp4s = sorted(cand.glob("*.mp4"))
    return mp4s[0] if mp4s else None


def unit_from_path(path: Path) -> str | None:
    for part in path.parts:
        m = _UNIT_RE.fullmatch(part) or _UNIT_RE.search(part)
        if m and part.startswith("EP"):
            return f"{m.group(1).upper()}-U{m.group(2)}"
    return None


def candidate_dirs(out_dir: Path) -> list[Path]:
    dirs: list[Path] = []
    for unit_dir in sorted(out_dir.glob("EP*-U*")):
        if not unit_dir.is_dir():
            continue
        for seed in sorted(unit_dir.glob("S*")):
            if seed.is_dir():
                # profiled stores under <download>/<filename_prefix>/
                nested = [p for p in seed.iterdir() if p.is_dir()]
                if nested:
                    dirs.extend(nested)
                else:
                    dirs.append(seed)
    return dirs


def dialogue_qc(unit: str, cand: Path, mp4: Path, report_dir: Path) -> dict:
    job = _JOB.get(unit)
    if not job:
        return {"ok": False, "reason": "no job map"}
    src = job / "assets" / "prompt_source.txt"
    expected = extract_expected_dialogue(src.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="pilot-dlg-") as tmp:
        wav = Path(tmp) / "a.wav"
        mp4_to_wav(mp4, wav)
        heard, segments = transcribe_wav_faster_whisper(wav)
    verdict = score_transcript(heard=heard, segments=segments, expected=expected)
    row = {
        "unit": unit,
        "cand": str(cand),
        "mp4": str(mp4),
        "ok": verdict.ok,
        "reason": verdict.reason,
        "overlap": verdict.overlap,
        "missing": list(verdict.missing or []),
        "extras": list(verdict.extras or []),
        "silent_expected": expected.silent,
        "transcript": heard,
        "segments": [{"start": a, "end": b, "text": t} for a, b, t in segments],
        "at": utc_now(),
    }
    out = cand / "dialogue_check.json"
    out.write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (report_dir / f"{unit}_{cand.name}_dialogue.json").write_text(
        json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return row


def audit_qc(unit: str, cand: Path) -> dict:
    marker = cand / "candidate_audit.json"
    if marker.is_file():
        return {"ok": True, "skipped": "exists"}
    cmd = [
        sys.executable,
        str(ROOT / "scripts/ops/audit_candidate.py"),
        unit,
        str(cand),
    ]
    env = {**os.environ, "PYTHONPATH": "src"}
    rc = subprocess.call(cmd, cwd=str(ROOT), env=env)
    return {"ok": rc == 0, "rc": rc}


def vision_plan_row(unit: str, cand: Path, dlg: dict) -> dict:
    job = _JOB.get(unit)
    risks = []
    if job:
        risks = scan_render_risks((job / "assets" / "prompt_source.txt").read_text(encoding="utf-8"))
    high = high_risk_codes(risks)
    l2 = "E" in high or unit in {"EP43-U06", "EP19-U06"}  # dual-shot dialogue
    return {
        "unit": unit,
        "cand": str(cand),
        "L0_codes": [r.code for r in risks],
        "L1_ok": dlg.get("ok"),
        "L1_reason": dlg.get("reason"),
        "L2_required": l2,
        "note": "run comfy-h3-unit-visual-qc on L2_required / L1 fail",
        "at": utc_now(),
    }


def refresh_plan(out_dir: Path, report_dir: Path, batch: str) -> None:
    subprocess.check_call(
        [
            sys.executable,
            str(ROOT / "scripts/ops/post_local_pilot_qc.py"),
            "--batch",
            batch,
            "--out-dir",
            str(out_dir),
            "--report-dir",
            str(report_dir),
        ],
        cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": "src"},
    )


def process_one(
    cand: Path,
    report_dir: Path,
    rolling: Path,
    out_dir: Path,
    *,
    batch: str,
    run_l3: bool = False,
) -> bool:
    mp4 = find_mp4(cand)
    meta = cand / "run_meta.json"
    if not mp4 or not meta.is_file():
        return False
    done = cand / ".pilot_qc_done"
    if done.is_file():
        return False
    unit = unit_from_path(cand) or unit_from_path(cand.parent) or unit_from_path(cand.parent.parent)
    if not unit or unit not in _JOB:
        # try parent Sxx / EPxx-Uyy
        for p in [cand.parent, cand.parent.parent]:
            unit = unit_from_path(p)
            if unit in _JOB:
                break
    if unit not in _JOB:
        print(f"SKIP_QC no unit map {cand}", flush=True)
        done.write_text("skip\n")
        return False

    print(f"QC_START {unit} {cand.name} {mp4.name}", flush=True)
    try:
        dlg = dialogue_qc(unit, cand, mp4, report_dir)
        print(
            f"QC_DIALOGUE {unit} ok={dlg.get('ok')} reason={dlg.get('reason')!r}",
            flush=True,
        )
    except Exception as exc:
        dlg = {"ok": False, "reason": f"dialogue_exc:{exc}"}
        print(f"QC_DIALOGUE_FAIL {unit} {exc}", flush=True)

    try:
        aud = audit_qc(unit, cand)
        print(f"QC_AUDIT {unit} {aud}", flush=True)
    except Exception as exc:
        print(f"QC_AUDIT_FAIL {unit} {exc}", flush=True)

    # L3 blooper triage (opt-in): anatomy/props chaos rank for human scan
    if run_l3:
        try:
            l3 = subprocess.run(
                [
                    "uv",
                    "run",
                    "--no-project",
                    "--script",
                    str(ROOT / "scripts/ops/pilot_l3_blooper_screen.py"),
                    "--cand",
                    str(cand),
                    "--unit",
                    unit,
                    "--batch",
                    batch,
                    "--allow-model-upload",
                    "--model",
                    "grok-4.7-low",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=600,
            )
            print(
                f"QC_L3 {unit} rc={l3.returncode} {(l3.stdout or '')[-300:]}",
                flush=True,
            )
            if l3.stderr:
                print(f"QC_L3_ERR {unit} {l3.stderr[-400:]}", flush=True)
        except Exception as exc:
            print(f"QC_L3_FAIL {unit} {exc}", flush=True)

    plan = vision_plan_row(unit, cand, dlg)
    plans = report_dir / "visual_qc_plan.jsonl"
    with plans.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(plan, ensure_ascii=False) + "\n")

    line = (
        f"| {utc_now()} | {unit} | {cand.parent.name}/{cand.name} | "
        f"L1={'PASS' if dlg.get('ok') else 'FAIL'} | {dlg.get('reason','')} | "
        f"L2={'yes' if plan['L2_required'] else 'no'} |\n"
    )
    if not rolling.is_file():
        rolling.write_text(
            "# Pilot ABCD rolling QC\n\n"
            "| at | unit | cand | L1 | reason | L2_vision |\n"
            "|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )
    with rolling.open("a", encoding="utf-8") as fh:
        fh.write(line)

    done.write_text(utc_now() + "\n", encoding="utf-8")
    try:
        refresh_plan(out_dir, report_dir, batch)
        tick = report_dir / "tick_status.txt"
        if tick.is_file():
            print(f"QC_TICK {tick.read_text(encoding='utf-8').strip()}", flush=True)
    except Exception as exc:
        print(f"QC_PLAN_REFRESH_FAIL {exc}", flush=True)
    print(f"QC_DONE {unit} {cand}", flush=True)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--expect", type=int, default=14)
    ap.add_argument("--poll", type=float, default=20)
    ap.add_argument("--batch", default="lihun-v23-pilot-abcd-1024")
    ap.add_argument(
        "--report-dir",
        type=Path,
        default=None,
    )
    ap.add_argument(
        "--runner-pid-file",
        type=Path,
        default=ROOT / "runs" / "lihun_v23_pilot_abcd_1024.pid",
    )
    ap.add_argument(
        "--l3",
        action="store_true",
        help="Run L3 blooper triage on each new cand (default off; prefer winners/batch)",
    )
    args = ap.parse_args()
    report_dir = args.report_dir or (ROOT / "runs" / "visual_qc" / args.batch)
    report_dir.mkdir(parents=True, exist_ok=True)
    rolling = report_dir / "rolling.md"
    print(
        f"QC_SIDECAR out={args.out_dir} report={report_dir} batch={args.batch} "
        f"l3={'on' if args.l3 else 'off'}",
        flush=True,
    )
    try:
        refresh_plan(args.out_dir, report_dir, args.batch)
    except Exception as exc:
        print(f"QC_PLAN_INIT_FAIL {exc}", flush=True)

    while True:
        for cand in candidate_dirs(args.out_dir):
            process_one(
                cand,
                report_dir,
                rolling,
                args.out_dir,
                batch=args.batch,
                run_l3=args.l3,
            )
        mp4_n = len(list(args.out_dir.rglob("*.mp4")))
        runner_alive = False
        if args.runner_pid_file.is_file():
            try:
                pid = int(args.runner_pid_file.read_text().strip())
                runner_alive = Path(f"/proc/{pid}").exists()
            except ValueError:
                runner_alive = False
        if mp4_n >= args.expect and not runner_alive:
            for cand in candidate_dirs(args.out_dir):
                process_one(
                    cand,
                    report_dir,
                    rolling,
                    args.out_dir,
                    batch=args.batch,
                    run_l3=args.l3,
                )
            try:
                refresh_plan(args.out_dir, report_dir, args.batch)
            except Exception as exc:
                print(f"QC_PLAN_FINAL_FAIL {exc}", flush=True)
            (report_dir / "QC_SIDECAR_DONE").write_text(utc_now() + "\n", encoding="utf-8")
            print(f"QC_SIDECAR_DONE mp4={mp4_n}", flush=True)
            return 0
        time.sleep(args.poll)


if __name__ == "__main__":
    raise SystemExit(main())
