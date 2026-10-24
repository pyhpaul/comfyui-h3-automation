"""Verify literal projections and raw model receipts without approving rollout."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from adaptive_visual_qc import digest, read, save
from comfy_orch.av_review.cli_screen import decode_final, image_read_coverage
from comfy_orch.av_review.compact import validate_payload_answer
from comfy_orch.av_review.workorders import constraint_disposition


def verify_entry(entry, output):
    path, parent = ROOT / entry["input"], ROOT / entry["parent_workorder"]
    if digest(path) != entry["input_sha256"] or digest(parent) != entry["parent_sha256"]:
        raise ValueError("Input/parent hash mismatch")
    payload, work = read(path), read(parent)
    if digest(ROOT / work["source"]["path"]) != work["source"]["sha256"]:
        raise ValueError("Source hash mismatch")
    for block in payload["source_evidence"]:
        for position in block.get("occurrences") or [block]:
            if work["source_expectations"][position["start"]:position["end"]] != block["text"]:
                raise ValueError("Projected source text differs from original")
    for candidate in payload["constraint_candidates"]:
        if work["source_expectations"][candidate["start"]:candidate["end"]] != candidate["quote"]:
            raise ValueError("Constraint quote differs from original")
    for image in payload["images"]:
        if digest(ROOT / image["path"]) != image["sha256"]:
            raise ValueError("Image hash mismatch")
    folder = output / entry["unit"] / entry["variant"] / "attempt-01"
    if not (folder / "result.json").exists():
        return None
    result = read(folder / "result.json")
    events = [json.loads(line) for line in (folder / "raw.jsonl").read_text().splitlines()]
    coverage = image_read_coverage(events, {str((ROOT / i["path"]).resolve()) for i in payload["images"]})
    if coverage != result.get("coverage"):
        raise ValueError("Image receipts mismatch")
    answer = result.get("answer")
    if answer and decode_final(events) != answer:
        raise ValueError("Model final answer mismatch")
    errors = validate_payload_answer(answer, work, payload) if answer else ["No final answer"]
    return {"unit": entry["unit"], "variant": entry["variant"], "input_characters": entry["input_characters"],
            "result": result, "initial_validation": read(folder / "validation.json"),
            "post_validation_errors": errors,
            "constraint_queue": [{"id": c["id"], "route": constraint_disposition(c)}
                                 for c in (answer or {}).get("constraint_checks", [])],
            "deferred_constraints": payload["deferred_constraints"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", required=True)
    args = parser.parse_args()
    output = ROOT / args.batch
    entries = read(output / "batch.json")["entries"]
    records = [verify_entry(entry, output) for entry in entries]
    attempted = [record for record in records if record]
    images = {}
    for entry in entries:
        payload = read(ROOT / entry["input"])
        key = [(i["frame_id"], i["sha256"]) for i in payload["images"]]
        if entry["unit"] in images and images[entry["unit"]] != key:
            raise ValueError("Paired image bytes differ")
        images[entry["unit"]] = key
    summary = {"verified_units": len(images), "prepared_variants": len(entries),
               "attempts": len(attempted), "valid_post_contract": sum(not r["post_validation_errors"] for r in attempted),
               "actual_image_reads": sum(r["result"]["coverage"]["completed_image_reads"] for r in attempted),
               "full_input_characters": sum(e["input_characters"] for e in entries if e["variant"] == "full"),
               "compact_input_characters": sum(e["input_characters"] for e in entries if e["variant"] == "compact"),
               "automatic_rollout": False, "L2": "NOT_DONE"}
    save(output / "verified-comparison.json", {"summary": summary, "attempts": attempted})
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
