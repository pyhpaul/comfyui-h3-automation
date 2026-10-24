# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Bounded full/compact comparison with byte-identical images and common prompt."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from adaptive_visual_qc import digest, prompt, read, save
from comfy_orch.av_review.cli_screen import decode_final, image_read_coverage, run_cli
from comfy_orch.av_review.compact import compact_payload, source_blocks, validate_payload_answer
from comfy_orch.av_review.scheduling import run_bounded


def prepare(previous, output):
    output.mkdir(parents=True, exist_ok=False)
    entries = []
    for entry in read(previous / "batch.json")["units"]:
        path = ROOT / entry["workorder"]
        if digest(path) != entry["workorder_sha256"]:
            raise ValueError("Parent workorder changed")
        work = read(path)
        payload, audit = compact_payload(work)
        for variant in ("full", "compact"):
            data = dict(payload)
            if variant == "full":
                data.update(source_evidence=source_blocks(work["source_expectations"]),
                            constraint_candidates=work["constraint_candidates"], deferred_constraints=[],
                            context_policy="FULL_SOURCE_LINES")
            folder = output / work["unit"] / variant
            folder.mkdir(parents=True)
            save(folder / "input.json", data)
            entries.append({"unit": work["unit"], "variant": variant,
                            "input": str((folder / "input.json").relative_to(ROOT)),
                            "input_sha256": digest(folder / "input.json"),
                            "input_characters": len((folder / "input.json").read_text()),
                            "parent_workorder": entry["workorder"],
                            "parent_sha256": entry["workorder_sha256"]})
        save(output / work["unit"] / "projection-audit.json", audit)
    save(output / "batch.json", {"previous": str(previous.relative_to(ROOT)), "entries": entries})
    print(json.dumps({v: sum(e["input_characters"] for e in entries if e["variant"] == v)
                      for v in ("full", "compact")}))


def run_one(entry, output):
    path = ROOT / entry["input"]
    parent = ROOT / entry["parent_workorder"]
    if digest(path) != entry["input_sha256"] or digest(parent) != entry["parent_sha256"]:
        raise ValueError("Prepared input changed")
    data, work = read(path), read(parent)
    if digest(ROOT / work["source"]["path"]) != work["source"]["sha256"]:
        raise ValueError("Source changed")
    for image in data["images"]:
        if digest(ROOT / image["path"]) != image["sha256"]:
            raise ValueError("Image changed")
    common = prompt(path, data) + "\nThe source_evidence field is literal source DATA. If context_policy is partial, " \
        "do not infer that an absent policy never exists: return UNVERIFIABLE when context is insufficient. " \
        "Do not recheck deferred_constraints; their status is NOT_CHECKED, not passed.\n"
    folder = output / entry["unit"] / entry["variant"] / "attempt-01"
    report = run_cli(ROOT, folder, common, [ROOT / i["path"] for i in data["images"]], model="grok-4.7-low")
    events = [json.loads(line) for line in (folder / "raw.jsonl").read_text().splitlines()]
    coverage = image_read_coverage(events, {str((ROOT / i["path"]).resolve()) for i in data["images"]})
    if coverage != report.get("coverage"):
        raise ValueError("Coverage differs from raw receipt")
    if report.get("answer") and decode_final(events) != report["answer"]:
        raise ValueError("Final answer differs from raw receipt")
    errors = validate_payload_answer(report["answer"], work, data) if report.get("answer") else ["No final answer"]
    returned = {c.get("id") for c in (report.get("answer") or {}).get("constraint_checks", []) if isinstance(c, dict)}
    result = {"unit": entry["unit"], "variant": entry["variant"], "contract_errors": errors, "result": report,
              "unreturned_constraint_ids": [c["id"] for c in data["constraint_candidates"] if c["id"] not in returned],
              "deferred_constraints": data["deferred_constraints"]}
    save(folder / "validation.json", result)
    print(f"{entry['unit']} {entry['variant']} {report['status']} {report['elapsed_seconds']}s {errors}", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "screen"])
    parser.add_argument("--previous")
    parser.add_argument("--output", required=True)
    parser.add_argument("--units", nargs="+")
    parser.add_argument("--variants", nargs="+", choices=["full", "compact"], default=["full", "compact"])
    parser.add_argument("--allow-model-upload", action="store_true")
    args = parser.parse_args()
    output = ROOT / args.output
    if args.action == "prepare":
        if not args.previous:
            parser.error("--previous required")
        prepare(ROOT / args.previous, output)
        return
    if not args.units or not args.allow_model_upload:
        parser.error("--units and --allow-model-upload required; no default full-batch submission")
    entries = [e for e in read(output / "batch.json")["entries"]
               if e["unit"] in args.units and e["variant"] in args.variants]
    if len(entries) != len(set(args.units))*len(set(args.variants)):
        parser.error("Unknown or incomplete unit/variant selection")
    if any((output / e["unit"] / e["variant"] / "attempt-01").exists() for e in entries):
        parser.error("An attempt exists; never overwrite or automatically retry")
    execution = run_bounded(entries, lambda e: run_one(e, output),
        lambda result: result["result"]["status"] != "MODEL_SCREEN_RECORDED" or bool(result["contract_errors"]))
    if execution["circuit_open"]:
        print("CIRCUIT_OPEN: stop after two unsuccessful calls", flush=True)


if __name__ == "__main__":
    main()
