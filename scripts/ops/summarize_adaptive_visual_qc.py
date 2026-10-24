"""Revalidate captured receipts and report follow-up coverage, never film clearance."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from comfy_orch.av_review.cli_screen import decode_final, image_read_coverage
from comfy_orch.av_review.workorders import followup_disposition, validate_followup


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def check_hash(path, expected):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"Changed evidence: {path}")


def unit_report(root, entry):
    path = ROOT / entry["workorder"]
    check_hash(path, entry["workorder_sha256"])
    work = load(path)
    check_hash(ROOT / work["source"]["path"], work["source"]["sha256"])
    for image in work["images"]:
        check_hash(ROOT / image["path"], image["sha256"])
    directory = root / work["unit"] / "attempt-01"
    if not (directory / "result.json").exists():
        return {"unit": work["unit"], "status": "NOT_SUBMITTED_OR_INCOMPLETE", "workorder": work}
    result = load(directory / "result.json")
    events = [json.loads(line) for line in (directory / "raw.jsonl").read_text().splitlines()]
    coverage = image_read_coverage(events, {str((ROOT / f["path"]).resolve()) for f in work["images"]})
    if coverage != result.get("coverage"):
        raise ValueError("Image coverage differs from raw receipts")
    answer = result.get("answer")
    if answer and decode_final(events) != answer:
        raise ValueError("Model answer differs from raw receipts")
    errors = validate_followup(answer, work) if answer else ["No final answer"]
    checked = {item["id"] for item in (answer or {}).get("constraint_checks", []) if isinstance(item, dict)}
    return {"unit": work["unit"], "status": result["status"], "contract_errors": errors,
            "workorder": work, "result": result,
            "review_queue": [{"id": item["id"], "disposition": followup_disposition(item)}
                             for item in (answer or {}).get("claim_checks", [])],
            "unreturned_constraint_ids": [c["id"] for c in work["constraint_candidates"] if c["id"] not in checked]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", required=True)
    args = parser.parse_args()
    root = ROOT / args.batch
    batch = load(root / "batch.json")
    units = [unit_report(root, entry) for entry in batch["units"]]
    valid = [u for u in units if u["status"] == "MODEL_SCREEN_RECORDED" and not u["contract_errors"]]
    statuses = Counter(c["status"] for u in valid for c in u["result"]["answer"]["claim_checks"])
    classes = Counter(c["issue_class"] for u in valid for c in u["result"]["answer"]["claim_checks"])
    queues = Counter(item["disposition"] for u in valid for item in u["review_queue"])
    summary = {"source_hashes_match": len(units), "valid_units": len(valid),
               "planned_native_reads": sum(e["images"] for e in batch["units"]),
               "actual_native_reads": sum(u.get("result", {}).get("coverage", {}).get("completed_image_reads", 0) for u in units),
               "call_elapsed_sum_seconds": round(sum(u.get("result", {}).get("elapsed_seconds", 0) for u in units), 3),
               "wall_seconds": load(root / "results.json")["wall_seconds"],
               "claim_statuses_not_accuracy": dict(statuses), "claim_classes": dict(classes),
               "review_queue_counts_not_verdicts": dict(queues),
               "unreturned_constraint_count": sum(len(u.get("unreturned_constraint_ids", [])) for u in units),
               "deferred_frame_references": sum(len(u["workorder"]["selection"]["deferred"]) for u in units),
               "human_full_watch_count": 0, "L2": "NOT_DONE", "final_verdict": "NOT_ISSUED"}
    report = {"summary": summary, "units": units}
    with (root / "verified-report.json").open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    lines = ["# Adaptive still-only follow-up", "", "No audio; no continuous viewing; no final verdict.",
             "Previous navigation and native frames reused. Not a blind detection benchmark.", "",
             "```json", json.dumps(summary, ensure_ascii=False, indent=2), "```", ""]
    for unit in units:
        lines.extend([f"## {unit['unit']} / {unit['status']}", ""])
        originals = {c["id"]: c for c in unit["workorder"]["original_claims"]}
        for check in unit.get("result", {}).get("answer", {}).get("claim_checks", []):
            lines.extend([f"- {check['id']} original: {originals[check['id']]['observed']}",
                          f"  - {check['status']} / {check['issue_class']}: {check['reason']}"])
        lines.append(f"- Deferred: {unit['workorder']['selection']['deferred']}")
        lines.append(f"- Unreturned constraint IDs: {unit.get('unreturned_constraint_ids', [])}")
        lines.append("")
    with (root / "verified-report.md").open("x", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
