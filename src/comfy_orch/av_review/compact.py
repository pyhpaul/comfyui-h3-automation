"""Literal context projection, not semantic compression or script approval."""
from __future__ import annotations

import re

from .workorders import validate_followup


def source_blocks(source: str) -> list[dict]:
    records = []
    section = "PREAMBLE"
    for match in re.finditer(r"[^\n]+", source):
        text = match.group()
        heading = re.match(r"【([^】]+)】", text)
        if heading:
            section = heading[1]
        records.append({"start": match.start(), "end": match.end(), "section": section, "text": text})
    return records


def compact_payload(work: dict) -> tuple[dict, dict]:
    """Keep complete shot/blocking/continuity lines and candidate owner context.

    Exact duplicate lines are represented once with every original occurrence.
    Excluded lines are recorded, never represented as checked constraints.
    """
    source = work["source_expectations"]
    candidates = work["constraint_candidates"]
    selected = []
    excluded = []
    for block in source_blocks(source):
        contains = any(block["start"] <= c["start"] < block["end"] for c in candidates)
        keep = contains or block["text"].startswith("▲") or block["section"] in {
            "空间／朝向硬锁", "交出状态", "H3 latent 接入文字"}
        (selected if keep else excluded).append(block)
    groups = {}
    for block in selected:
        key = (block["section"], block["text"])
        if key not in groups:
            groups[key] = {"section": block["section"], "text": block["text"], "occurrences": []}
        groups[key]["occurrences"].append({"start": block["start"], "end": block["end"]})
    deferred = [c for c in candidates if "只有点名的说话人开口" in c["quote"]]
    payload = {"unit": work["unit"], "source_sha256": work["source"]["sha256"],
               "prompt_sha256": work["prompt_sha256"], "source_evidence": list(groups.values()),
               "constraint_candidates": [c for c in candidates if c not in deferred],
               "original_claims": work["original_claims"],
               "images": work["images"], "audio_included": False,
               "context_policy": "LITERAL_PARTIAL_CONTEXT_NOT_COMPLETE_SCRIPT",
               "missing_context_action": "UNVERIFIABLE_NOT_INVALID_EXPECTATION",
               "deferred_constraints": [{"id": c["id"], "reason": "NO_AUDIO_NOT_CHECKED"} for c in deferred]}
    audit = {"source_characters": len(source), "included_line_occurrences": len(selected),
             "included_unique_lines": len(groups), "excluded_lines": excluded,
             "complete_script": False, "source_in_workorder_unchanged": True}
    return payload, audit


def validate_payload_answer(answer: dict, work: dict, payload: dict) -> list[str]:
    """Allow only explicit, evidence-free echoes of known deferred constraints.

    Raw answers remain unchanged. A supported or frame-citing deferred check is
    never filtered away to make a validation pass.
    """
    checks = answer.get("constraint_checks")
    if not isinstance(checks, list):
        return validate_followup(answer, dict(work, constraint_candidates=payload["constraint_candidates"]))
    originals = {c["id"]: c for c in work["constraint_candidates"]}
    deferred = {c["id"] for c in payload["deferred_constraints"]}
    active = []
    for check in checks:
        known = originals.get(str(check.get("id"))) if isinstance(check, dict) else None
        if known and check.get("id") in deferred and check.get("status") == "NOT_CHECKED" \
                and check.get("frame_ids") == [] and check.get("source_quote") in ("", known["quote"]):
            continue
        active.append(check)
    normalized = dict(answer, constraint_checks=active)
    errors = validate_followup(normalized, dict(work, constraint_candidates=payload["constraint_candidates"]))
    expected = {c["id"] for c in payload["constraint_candidates"]}
    returned = [str(c.get("id")) for c in active if isinstance(c, dict)]
    if len(returned) != len(expected) or set(returned) != expected:
        errors.append("Active constraints must each be checked exactly once; silence is not clearance")
    return errors
