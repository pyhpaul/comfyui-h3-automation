#!/usr/bin/env python3
"""Full post-render QC plan for a *local* pilot batch (no Feiniu).

Mirrors ``post_feiniu_unit_qc.py``: L0 prompt risk + L1 dialogue rows already
written beside each mp4 by ``watch_pilot_qc_sidecar.py``, then emits
``runs/visual_qc/<batch>/plan.json`` + ``plan.md`` for ``comfy-h3-unit-visual-qc``.

  PYTHONPATH=src python scripts/ops/post_local_pilot_qc.py \
    --batch lihun-v23-pilot-abcd-1024 \
    --out-dir .cache/lihun_v23_pilot_abcd_1024
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from comfy_orch.pack_render_risk import high_risk_codes, scan_render_risks  # noqa: E402

_UNIT_RE = re.compile(r"(EP\d+)-U(\d+)", re.I)
_JOB = {
    "EP11-U04": ROOT / "jobs/ep_units/EP11-继母-v23-U04",
    "EP43-U06": ROOT / "jobs/ep_units/EP43-继母-v23-U06",
    "EP19-U06": ROOT / "jobs/ep_units/EP19-继母-v23-U06",
    "EP57-U08": ROOT / "jobs/ep_units/EP57-继母-v23-U08",
}


def _slug(batch: str) -> str:
    return re.sub(r"[^\w\-]+", "_", batch).strip("_")[:80]


def _sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _unit_tag(path: Path) -> str | None:
    for part in path.parts:
        m = _UNIT_RE.search(part)
        if m:
            return f"{m.group(1).upper()}-U{m.group(2)}"
    return None


def iter_candidates(out_dir: Path) -> list[tuple[str, Path, Path]]:
    """Yield (unit, cand_dir, mp4)."""
    rows: list[tuple[str, Path, Path]] = []
    for mp4 in sorted(out_dir.rglob("*.mp4")):
        cand = mp4.parent
        unit = _unit_tag(cand) or _unit_tag(cand.parent) or _unit_tag(cand.parent.parent)
        if not unit:
            continue
        rows.append((unit, cand, mp4))
    return rows


def l0_for_job(unit: str) -> dict:
    job = _JOB.get(unit)
    if not job:
        return {
            "unit": unit,
            "L0_unit_risk": "UNKNOWN",
            "L0_codes": [],
            "L2_required": False,
            "prompt_path": None,
            "prompt_sha256": None,
        }
    src = job / "assets" / "prompt_source.txt"
    text = src.read_text(encoding="utf-8")
    risks = scan_render_risks(text)
    high = high_risk_codes(risks)
    # Dual-shot dialogue units always need L2 speaker watch in this pilot.
    dual = unit in {"EP43-U06", "EP19-U06"} or "E" in high
    silent_b = unit == "EP11-U04" or "B" in high
    risk = "HIGH" if (dual or silent_b or high) else ("MED" if risks else "LOW")
    return {
        "unit": unit,
        "job_dir": str(job.relative_to(ROOT)),
        "L0_unit_risk": risk,
        "L0_codes": [r.code for r in risks],
        "L0_messages": [r.message for r in risks],
        "L2_required": bool(dual),
        "L2_reason": "dual-shot dialogue / chorus risk" if dual else (
            "silent-unit mouth lock verify" if silent_b else ""
        ),
        "prompt_path": str(src.relative_to(ROOT)),
        "prompt_sha256": _sha(src),
    }


def _read_l2_status(cand: Path) -> str | None:
    path = cand / "l2_status.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "WATCH_INCOMPLETE"
    status = str(payload.get("status") or "").strip().upper()
    return status or "WATCH_INCOMPLETE"


def _unit_l2_status(required: bool, cands: list[dict]) -> str:
    if not required:
        return "N/A"
    statuses = [c.get("L2_cand_status") for c in cands if c.get("L2_cand_status")]
    if not statuses:
        return "NOT_DONE"
    if any(s in {"WATCH_INCOMPLETE", "NOT_DONE", "REQUIRED"} for s in statuses):
        return "WATCH_INCOMPLETE"
    if all(s in {"DONE", "PASS", "FAIL", "CLEARED"} for s in statuses):
        # Any decided watch counts as done for close-gate (verdict may still be FAIL).
        return "DONE"
    return "WATCH_INCOMPLETE"


def l2_blocks_close(plan: dict) -> bool:
    """Dual-shot L2 must not stay WATCH_INCOMPLETE / NOT_DONE when closing a batch."""
    for unit in plan.get("units") or []:
        if not unit.get("L2_required"):
            continue
        status = unit.get("L2_status") or "NOT_DONE"
        if status in {"NOT_DONE", "WATCH_INCOMPLETE", "REQUIRED"}:
            return True
    return False


def build_plan(batch: str, out_dir: Path) -> dict:
    cand_rows = iter_candidates(out_dir)
    by_unit: dict[str, list[dict]] = {}
    for unit, cand, mp4 in cand_rows:
        dlg_path = cand / "dialogue_check.json"
        audit_path = cand / "candidate_audit.json"
        l3_path = cand / "l3_screen.json"
        l3c_path = cand / "l3_confirm.json"
        dlg = {}
        if dlg_path.is_file():
            dlg = json.loads(dlg_path.read_text(encoding="utf-8"))
        l3 = {}
        if l3_path.is_file():
            l3 = json.loads(l3_path.read_text(encoding="utf-8"))
        l3c = {}
        if l3c_path.is_file():
            l3c = json.loads(l3c_path.read_text(encoding="utf-8"))
        entry = {
            "cand": str(cand.relative_to(ROOT)) if cand.is_relative_to(ROOT) else str(cand),
            "mp4": str(mp4.relative_to(ROOT)) if mp4.is_relative_to(ROOT) else str(mp4),
            "media_sha256": _sha(mp4),
            "L1_ok": dlg.get("ok"),
            "L1_reason": dlg.get("reason"),
            "L1_overlap": dlg.get("overlap"),
            "audit": audit_path.is_file(),
            "human_review": (cand / "human_review.json").is_file(),
            "L3_status": l3.get("L3_status") or "NOT_RUN",
            "L3_triage": l3.get("triage_risk") or "NONE",
            "L3_suspects": l3.get("suspect_count"),
            "L3_confirm": l3c.get("status"),
            "L2_cand_status": _read_l2_status(cand),
            "qc_done": (cand / ".pilot_qc_done").is_file(),
        }
        by_unit.setdefault(unit, []).append(entry)

    # Always include A-class cut note even without new mp4
    units_out = []
    for unit in sorted(set(list(_JOB) + list(by_unit))):
        base = l0_for_job(unit)
        cands = by_unit.get(unit, [])
        l1_fail = [c for c in cands if c.get("L1_ok") is False]
        l1_pass = [c for c in cands if c.get("L1_ok") is True]
        if unit == "EP57-U08":
            base["L0_unit_risk"] = "A_CUT"
            base["L2_required"] = False
            base["note"] = "prefer_relaxed_cut; see EDIT_NOTE in out-dir"
        l2_status = _unit_l2_status(bool(base.get("L2_required")), cands)
        triage_rank = {"HIGH": 3, "MED": 2, "LOW": 1, "NONE": 0}
        l3_triage = "NONE"
        for c in cands:
            t = (c.get("L3_triage") or "NONE").upper()
            if triage_rank.get(t, 0) > triage_rank.get(l3_triage, 0):
                l3_triage = t
        l3_status = "NOT_RUN"
        for prefer in (
            "SUSPECTS_OPEN",
            "TRIAGE_PARTIAL",
            "SCREENED_NO_SUSPECTS",
            "SCREEN_INCOMPLETE",
        ):
            if any(c.get("L3_status") == prefer for c in cands):
                l3_status = prefer
                break
        base.update(
            {
                "candidates": cands,
                "L1_pass": len(l1_pass),
                "L1_fail": len(l1_fail),
                "L1_status": (
                    "PASS"
                    if l1_pass and not l1_fail
                    else ("MIXED" if l1_pass and l1_fail else ("FAIL" if l1_fail else "PENDING"))
                ),
                "L2_status": l2_status,
                "L3_status": l3_status,
                "L3_triage": l3_triage,
                "L3_confirm_pending": any(
                    (c.get("L3_confirm") or "")
                    in {
                        "AWAITING_CONFIRM",
                        "TRIAGE_HIGH_REVIEW_FIRST",
                        "TRIAGE_QUEUE",
                        "SCREENED_NO_SUSPECTS_PENDING_HUMAN",
                    }
                    for c in cands
                ),
            }
        )
        units_out.append(base)

    high = [u for u in units_out if u.get("L0_unit_risk") == "HIGH" or u.get("L2_required")]
    l3_high = [u["unit"] for u in units_out if u.get("L3_triage") == "HIGH"]
    l3_med = [u["unit"] for u in units_out if u.get("L3_triage") == "MED"]
    l3_pending = [u["unit"] for u in units_out if u.get("L3_confirm_pending")]
    # Human scan order: L3 HIGH triage first, then dual-shot L2, then other HIGH L0.
    spot_order = list(
        dict.fromkeys(
            l3_high
            + l3_med
            + [u["unit"] for u in high]
            + l3_pending
        )
    )
    plan = {
        "schema": "visual_qc_plan/v1",
        "batch": batch,
        "delivery": "local_only",
        "out_dir": str(out_dir),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "policy": (
            "Full flow except Feiniu: L0 ∥ L1 ASR ∥ audit_candidate ∥ "
            "optional L3 blooper TRIAGE (risk rank; soft frame-id; winners/batch only); "
            "L2 speaker watch hard-required for dual-shot (no WATCH_INCOMPLETE close); "
            "no auto-remake; local out_dir only."
        ),
        "banner": (
            "L0+L1 armed; L3 triage optional (HIGH first for human scan); "
            "L2 dual-shot must be DONE before close; triage ≠ clear bill"
        ),
        "units": units_out,
        "human_spot_check": {
            "priority": (
                "L3 triage HIGH anatomy/props → MED → dual-shot chorus L2 → "
                "silent mouth → short-Q"
            ),
            "suggested_units": spot_order[:8] or [u["unit"] for u in high],
            "l3_triage_high": l3_high,
            "l3_triage_med": l3_med,
            "l3_confirm_units": l3_pending,
            "per_episode_cap": 2,
        },
        "candidate_mp4_count": len(cand_rows),
    }
    plan["L2_blocks_close"] = l2_blocks_close(plan)
    return plan


def write_tick_status(plan: dict, report_dir: Path) -> Path:
    """One-line status for 5m monitor / chat writeback (not a clear bill)."""
    units = plan.get("units") or []
    l1_fail = sum(1 for u in units if u.get("L1_status") == "FAIL")
    l1_pass = sum(1 for u in units if u.get("L1_status") == "PASS")
    l2_block = [u["unit"] for u in units if u.get("L2_required") and u.get("L2_status") != "DONE"]
    spot = plan.get("human_spot_check") or {}
    l3_high = spot.get("l3_triage_high") or [
        u["unit"] for u in units if u.get("L3_triage") == "HIGH"
    ]
    line = (
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} "
        f"mp4={plan.get('candidate_mp4_count')} "
        f"L1_pass={l1_pass} L1_fail={l1_fail} "
        f"L2_block={','.join(l2_block) or '-'} "
        f"L3_high={','.join(l3_high) or '-'} "
        f"close_blocked={plan.get('L2_blocks_close')}"
    )
    path = report_dir / "tick_status.txt"
    path.write_text(line + "\n", encoding="utf-8")
    hist = report_dir / "tick_status.log"
    with hist.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return path


def write_plan(plan: dict, report_dir: Path) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "plan.json"
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_tick_status(plan, report_dir)
    lines = [
        f"# Visual QC plan — {plan['batch']} (local)",
        "",
        f"- Banner: {plan.get('banner')}",
        f"- mp4 candidates: {plan.get('candidate_mp4_count')}",
        f"- Delivery: local only (`{plan.get('out_dir')}`)",
        f"- L2 blocks close: {plan.get('L2_blocks_close')}",
        f"- Next: L2 watch on L2_required until DONE; pick winners; no Feiniu",
        "",
        "| unit | L0 | L1 | L2_req | L2 | L3 | L3_triage | cands |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for u in plan["units"]:
        lines.append(
            f"| {u['unit']} | {u.get('L0_unit_risk')} | {u.get('L1_status')} | "
            f"{u.get('L2_required')} | {u.get('L2_status')} | {u.get('L3_status')} | "
            f"{u.get('L3_triage') or 'NONE'} | "
            f"{len(u.get('candidates') or [])} |"
        )
    (report_dir / "plan.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch", default="lihun-v23-pilot-abcd-1024")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument(
        "--report-dir",
        type=Path,
        default=None,
        help="default: runs/visual_qc/<batch_slug>",
    )
    args = ap.parse_args()
    report_dir = (args.report_dir or (ROOT / "runs" / "visual_qc" / _slug(args.batch))).resolve()
    plan = build_plan(args.batch, args.out_dir.resolve())
    path = write_plan(plan, report_dir)
    try:
        plan_rel = str(path.relative_to(ROOT))
    except ValueError:
        plan_rel = str(path)
    print(
        json.dumps(
            {
                "plan": plan_rel,
                "units": len(plan["units"]),
                "mp4": plan["candidate_mp4_count"],
                "l2": [u["unit"] for u in plan["units"] if u.get("L2_required")],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
