"""Pure workorder decisions; no media I/O or model-derived final verdicts."""
from __future__ import annotations

import re


MARKERS = re.compile(r"已经脱下|刚脱下|在镜头外|没有入画|不得入画|敞着穿|床头灯不开|不戴戒指|只有|唯一|只剩|不得有其它")
EXCLUSIVE = re.compile(r"只有|唯一|只剩|不得有其它")


def constraint_candidates(source: str) -> list[dict]:
    """Locate literal clauses, not a complete or accepted constraint parser."""
    records = []
    for match in re.finditer(r"[^。；;\n]+[。；;]?", source):
        quote = match.group()
        if MARKERS.search(quote) and len(quote) <= 600:
            records.append({"id": f"C{len(records)+1}", "quote": quote,
                            "start": match.start(), "end": match.end(),
                            "exclusive_word_present": bool(EXCLUSIVE.search(quote)),
                            "status": "CANDIDATE_NOT_ACCEPTED", "scope": "UNRESOLVED"})
    return records


def adaptive_frames(claims: list[dict], available: list[str], anchors: list[str],
                    budget: int = 6) -> dict:
    """Cover anchors and one frame per claim; add context to the top risk only."""
    if not 1 <= budget <= 12:
        raise ValueError("Frame budget must be between 1 and 12")
    valid = set(available)
    if any(frame not in valid for frame in anchors):
        raise ValueError("Unknown mandatory anchor")
    if len(set(anchors)) > budget:
        raise ValueError("Mandatory anchors exceed budget")
    priorities = {"anatomy": 0, "wardrobe_continuity": 1, "prop_continuity": 1}
    ranked = sorted(claims, key=lambda claim: priorities.get(claim.get("category"), 2))
    requests = list(anchors)
    groups = []
    for claim in ranked:
        ids = claim.get("detail_frame_ids") or claim.get("frame_ids", [])
        ids = list(dict.fromkeys(frame for frame in ids if frame in valid))
        groups.append(ids)
        requests.extend(ids[:1])
    # Neighbors are context, not evidence that an entire transition was watched.
    context = groups[0][:1] if groups and priorities.get(ranked[0].get("category"), 2) < 2 else []
    for frame in context:
        index = available.index(frame)
        requests.extend(available[max(0, index-1):index])
        requests.extend(available[index+1:index+2])
    ordered = list(dict.fromkeys(requests))
    selected = ordered[:budget]
    all_requested = list(dict.fromkeys(ordered + [frame for ids in groups for frame in ids]))
    return {"selected": selected, "deferred": [f for f in all_requested if f not in selected],
            "claim_coverage": [{"id": claim["id"],
                                "selected_cited_frames": [f for f in claim.get("frame_ids", []) if f in selected],
                                "unselected_cited_frames": [f for f in claim.get("frame_ids", []) if f not in selected]}
                               for claim in claims]}


def validate_followup(answer: dict, workorder: dict) -> list[str]:
    """Check contracts, not whether the model's visual interpretation is correct."""
    errors = []
    if answer.get("unit") != workorder["unit"]:
        errors.append("Wrong unit")
    if answer.get("audio_status") != "AUDIO_UNAVAILABLE" or answer.get("L2_status") != "NOT_DONE":
        errors.append("Invalid modality boundary")
    selected = {item["frame_id"] for item in workorder["images"]}
    checks = answer.get("claim_checks")
    originals = {item["id"]: item for item in workorder["original_claims"]}
    if not isinstance(checks, list):
        return errors + ["claim_checks must be a list"]
    if any(not isinstance(item, dict) for item in checks):
        return errors + ["Invalid claim check"]
    ids = [item.get("id") for item in checks]
    if len(ids) != len(originals) or set(map(str, ids)) != set(originals):
        errors.append("Original claims must each be resolved exactly once")
    allowed = {"SUPPORTED_STILL_SUSPECT", "NOT_SUPPORTED_IN_SELECTED_STILLS", "UNVERIFIABLE", "INVALID_EXPECTATION"}
    classes = {"VISUAL_ANOMALY", "SOURCE_DEVIATION", "INSUFFICIENT_EVIDENCE"}
    for item in checks:
        if str(item.get("status")) not in allowed or str(item.get("issue_class")) not in classes:
            errors.append("Invalid status or issue class")
        frames = item.get("frame_ids")
        if not isinstance(frames, list) or any(not isinstance(f, str) or f not in selected for f in frames):
            errors.append("Claim cites unread frames")
        elif item.get("status") == "SUPPORTED_STILL_SUSPECT" and not frames:
            errors.append("Supported suspect needs selected-frame evidence")
        if not isinstance(item.get("reason"), str) or not item["reason"].strip():
            errors.append("Claim needs reason")
    for field in ("constraint_checks", "new_observations", "limitations"):
        if not isinstance(answer.get(field), list):
            errors.append(f"{field} must be a list")
    constraints = {item["id"]: item for item in workorder["constraint_candidates"]}
    constraint_checks = answer.get("constraint_checks")
    for item in constraint_checks if isinstance(constraint_checks, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or item["id"] not in constraints:
            errors.append("Unknown source constraint")
            continue
        if item.get("source_quote") != constraints[item["id"]]["quote"]:
            errors.append("Source constraint quote changed")
        if str(item.get("status")) not in {"CONSISTENT_IN_STILLS", "POSSIBLE_SOURCE_DEVIATION", "UNVERIFIABLE", "OUT_OF_SCOPE"}:
            errors.append("Invalid constraint status")
        frames = item.get("frame_ids", [])
        if not isinstance(frames, list) or any(not isinstance(f, str) or f not in selected for f in frames):
            errors.append("Constraint cites unread frames")
        elif item.get("status") == "POSSIBLE_SOURCE_DEVIATION" and not frames:
            errors.append("Constraint deviation needs frame evidence")
    return errors


def followup_disposition(check: dict) -> str:
    """Route for review without translating a model label into a defect verdict."""
    status = check.get("status")
    if status == "INVALID_EXPECTATION":
        return "REJECT_EXPECTATION"
    if status == "NOT_SUPPORTED_IN_SELECTED_STILLS":
        return "WITHDRAW_ORIGINAL_ONLY"
    if status != "SUPPORTED_STILL_SUSPECT" or check.get("issue_class") == "INSUFFICIENT_EVIDENCE":
        return "NEEDS_EVIDENCE"
    if check.get("issue_class") == "SOURCE_DEVIATION":
        return "DIRECTOR_REVIEW"
    if check.get("issue_class") == "VISUAL_ANOMALY":
        return "VISUAL_REVIEW"
    return "NEEDS_EVIDENCE"


def constraint_disposition(check: dict) -> str:
    """A framing mismatch cannot silently close an explicit script constraint."""
    return {"POSSIBLE_SOURCE_DEVIATION": "DIRECTOR_REVIEW",
            "CONSISTENT_IN_STILLS": "PARTIAL_CHECK_NOT_CLEARANCE",
            "UNVERIFIABLE": "NEEDS_EVIDENCE", "OUT_OF_SCOPE": "SCOPE_REVIEW",
            "NOT_CHECKED": "DEFERRED_NOT_CHECKED"}.get(str(check.get("status")), "NEEDS_EVIDENCE")
