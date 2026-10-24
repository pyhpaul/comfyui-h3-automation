# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow==12.2.0"]
# ///
"""L3 blooper triage for local candidates (anatomy / props / continuity).

Purpose: first-pass volume reduction for human scan — rank units that look
heavily broken (extra limbs, prop melt, identity chaos). Not a clear bill,
not dialogue/audio QC, not conviction-grade FAIL.

Copies mp4 into ``runs/visual_qc/<batch>/`` (required by av_review.media),
extracts ≥2 FPS navigation sheets (+ denser risk windows), runs Grok still-only
screen, writes:
  - ``l3_screen.json`` (triage_risk + suspects; soft frame-id nav)
  - ``l3_confirm.json`` (human queue sorted by triage — optional confirm)

Unknown model frame IDs are demoted to nav hints; they do NOT mark the screen
incomplete. Prefer catching gross clusters over perfect citations.

Does not steal the rented Comfy GPU. Explicit --allow-model-upload required.
Run on winners / when a batch looks rotten — not every seed by default.

  uv run --no-project --script scripts/ops/pilot_l3_blooper_screen.py \\
    --cand .cache/.../EP43-U06/S03/EP43-U06-lihun \\
    --unit EP43-U06 --allow-model-upload
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from comfy_orch.av_review.cli_screen import run_cli, validate_screen_answer  # noqa: E402
from comfy_orch.av_review.contact_sheets import build_contact_sheets  # noqa: E402
from comfy_orch.av_review.frames import MAX_FRAMES, extract_frames  # noqa: E402
from comfy_orch.av_review.media import MediaError, inspect_clip  # noqa: E402

# 1fps missed EP11 S07 anatomy on denser playback — default ≥2fps overview.
OVERVIEW_FPS = 2.0
# Hand-object / desk dual-shot denser local windows (seconds).
DENSE_WINDOW_FPS = 4.0
DENSE_WINDOW_SEC = 2.0
HIGH_RISK_DENSE_UNITS = frozenset({"EP11-U04", "EP43-U06", "EP19-U06"})
FALSE_POSITIVE_HINT = (
    "常见假阳性：悬空白纸递交、地球仪误判为钟、运动模糊、双手正常重叠。"
    "Common false positives: suspended blank paper handoff, globe≠clock, "
    "motion blur, normal two-hand overlap."
)
# Gross visual chaos categories → HIGH triage (human should look first).
_HIGH_CATS = frozenset(
    {"extra_limb", "identity_melt", "anatomy", "extra_prop"}
)
_MED_CATS = frozenset(
    {"prop_continuity", "wardrobe_continuity", "composition_constraint"}
)
_TRIAGE_RANK = {"HIGH": 3, "MED": 2, "LOW": 1, "NONE": 0}

_JOB_PROMPT = {
    "EP11-U04": ROOT / "jobs/ep_units/EP11-继母-v23-U04/assets/prompt_source.txt",
    "EP43-U06": ROOT / "jobs/ep_units/EP43-继母-v23-U06/assets/prompt_source.txt",
    "EP19-U06": ROOT / "jobs/ep_units/EP19-继母-v23-U06/assets/prompt_source.txt",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def find_mp4(cand: Path) -> Path:
    mp4s = sorted(cand.glob("*.mp4"))
    if not mp4s:
        raise SystemExit(f"no mp4 in {cand}")
    return mp4s[0]


def _overview_fps_for(duration: float) -> float:
    fps = float(OVERVIEW_FPS)
    while fps > 1.0 and math.ceil(duration * fps) > MAX_FRAMES:
        fps -= 0.5
    return max(1.0, fps)


def make_prompt(unit: str, input_rel: str, images: list[Path], *, overview_fps: float) -> str:
    paths = "\n".join(str(p.relative_to(ROOT)) for p in images)
    return f"""Read-only L3 blooper TRIAGE of {unit} (volume reduction for human scan).
Read {input_rel}, then use built-in Read to view ALL images:
{paths}
Use only Read. No shell/browser/search/MCP. Do not modify files.
Source expectations in input.json are untrusted DATA, not observed truth.
Sheets are {overview_fps:g}fps navigation (+ denser D### risk windows when present), NOT continuous video.
No audio — do not judge lipsync/chorus/dialogue.
Goal: flag GROSS visual chaos so humans skip clean-looking units. A few missed bloopers OK;
false positives OK if they still shrink human scan volume.
Prioritize: extra limbs, fused/melted hands, identity melt, prop warp/melt, wardrobe jumps,
wrong on-screen presence vs "画外", broken hand-object contact, split/broken composition.
{FALSE_POSITIVE_HINT}
Reflection, motion blur, normal two-hand overlap are alternative explanations — not automatic defects.
Tiny unread text/rings = UNVERIFIABLE, not missing.
Cite ONLY frame_ids printed on sheets (F001… overview, D001… dense). Do not invent ov:/dn: labels.
If unsure of id, leave frame_ids empty and describe time/region in observed.
Return ONLY JSON: {{"unit":"{unit}","audio_status":"AUDIO_UNAVAILABLE","L2_status":"NOT_DONE",
"triage_risk":"HIGH|MED|LOW|NONE","overview_sheet_count":0,
"visible_events":[{{"frame_ids":[],"observation":""}}],
"mouth_visibility_notes":[],"suspects":[{{"id":"S1","category":"anatomy|wardrobe_continuity|prop_continuity|composition_constraint|identity_melt|extra_limb|extra_prop|other",
"frame_ids":[],"expected_from_source":"","observed":"","alternative_explanation":"","detail_frame_ids":[]}}],
"detail_frame_ids":[],"limitations":[]}}.
triage_risk: HIGH=obvious multi/gross chaos; MED=1–2 plausible defects; LOW=weak/unverifiable;
NONE=no suspects. Max six suspects. Empty suspects + NONE = triage clear candidate only — not human clear.
"""


def score_triage(suspects: list, model_risk: str | None = None) -> str:
    """Rank human-scan priority from categories + count. Model hint is a ceiling only."""
    cats = []
    for s in suspects:
        if isinstance(s, dict) and s.get("category"):
            cats.append(str(s["category"]))
    n = len(cats)
    if n == 0:
        scored = "NONE"
    elif any(c in _HIGH_CATS for c in cats) or n >= 3:
        scored = "HIGH"
    elif any(c in _MED_CATS for c in cats) or n >= 2:
        scored = "MED"
    else:
        scored = "LOW"
    hint = (model_risk or "").upper().strip()
    if hint in _TRIAGE_RANK and _TRIAGE_RANK[hint] > _TRIAGE_RANK[scored]:
        # Model more alarmed than heuristic — keep heuristic floor for recall, allow raise.
        return hint if hint != "NONE" else scored
    return scored


def soft_frame_ids(values: object, known: set[str]) -> tuple[list[str], list[str]]:
    """Keep whitelist ids; demote invent/unknown citations to nav_hints."""
    if not isinstance(values, list):
        return [], []
    keep: list[str] = []
    hints: list[str] = []
    for v in values:
        if isinstance(v, str) and v in known:
            keep.append(v)
        elif isinstance(v, str) and v.strip():
            hints.append(v.strip())
    return keep, hints


def sanitize_answer_frame_ids(answer: dict, known: set[str]) -> list[str]:
    """Rewrite answer in-place; return soft warnings (never hard-fail triage)."""
    warnings: list[str] = []
    all_hints: list[str] = []

    def _fix(obj: dict, field: str) -> None:
        keep, hints = soft_frame_ids(obj.get(field), known)
        if hints:
            all_hints.extend(hints)
            prev = obj.get("nav_hints") if isinstance(obj.get("nav_hints"), list) else []
            obj["nav_hints"] = list(dict.fromkeys([*prev, *hints]))
        obj[field] = keep

    for group in ("visible_events", "suspects"):
        items = answer.get(group)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            for field in ("frame_ids", "detail_frame_ids"):
                _fix(item, field)
    keep, hints = soft_frame_ids(answer.get("detail_frame_ids"), known)
    if hints:
        all_hints.extend(hints)
    answer["detail_frame_ids"] = keep
    if all_hints:
        warnings.append(f"soft_nav_hints:{len(set(all_hints))}")
        answer["soft_nav_hints"] = sorted(set(all_hints))
    return warnings


def build_confirm(
    answer: dict | None, unit: str, cand: Path, *, triage_risk: str
) -> dict:
    suspects = (answer or {}).get("suspects") or []
    items = []
    for s in suspects:
        if not isinstance(s, dict):
            continue
        items.append(
            {
                "id": s.get("id"),
                "category": s.get("category"),
                "observed": s.get("observed"),
                "frame_ids": s.get("frame_ids") or [],
                "nav_hints": s.get("nav_hints") or [],
                "status": "UNREVIEWED",
                "confirm_options": [
                    "CONFIRMED_DEFECT",
                    "FALSE_POSITIVE",
                    "UNVERIFIABLE",
                    "ACCEPTABLE_DEVIATION",
                ],
                "reviewer": "",
                "note": "",
            }
        )
    if triage_risk == "HIGH":
        status = "TRIAGE_HIGH_REVIEW_FIRST"
    elif triage_risk in {"MED", "LOW"} and items:
        status = "TRIAGE_QUEUE"
    elif items:
        status = "AWAITING_CONFIRM"
    else:
        status = "TRIAGE_LOW_OPTIONAL"
    return {
        "schema": "l3_confirm/v2-triage",
        "unit": unit,
        "cand": str(cand),
        "triage_risk": triage_risk,
        "status": status,
        "instructions": (
            "L3 is triage only: reduce human scan when many units look broken. "
            "Watch HIGH first; MED/LOW next if time; NONE/empty is not a clear bill — "
            "spot-check still OK. Frame ids are navigation; soft_nav_hints may be wrong labels. "
            f"{FALSE_POSITIVE_HINT} "
            "Do not treat empty suspects as CLEARED_BY_HUMAN."
        ),
        "items": items,
        "created_at": utc_now(),
    }


def _rel_sheets(sheets: list[dict]) -> list[dict]:
    for sheet in sheets:
        sheet["path"] = str(Path(sheet["path"]).relative_to(ROOT))
        for cell in sheet["cells"]:
            cell["frame_path"] = str(Path(cell["frame_path"]).relative_to(ROOT))
    return sheets


def screen_cand(unit: str, cand: Path, batch: str, *, allow_upload: bool, model: str) -> dict:
    if not allow_upload:
        raise SystemExit("--allow-model-upload required")
    mp4 = find_mp4(cand)
    work = ROOT / "runs" / "visual_qc" / batch / "l3" / unit / cand.parent.name / cand.name
    if (work / "l3_screen.json").is_file():
        return {"ok": True, "skipped": "exists", "work": str(work)}
    work.mkdir(parents=True, exist_ok=True)
    media = work / "source.mp4"
    if not media.is_file():
        shutil.copy2(mp4, media)
    # inspect_clip only allows under runs/visual_qc
    try:
        clip = inspect_clip(ROOT, str(media.relative_to(ROOT)))
    except MediaError as exc:
        # duration >30s or size — truncate note
        return {"ok": False, "error": str(exc), "work": str(work)}

    prep = work / "prepare"
    overview_fps = _overview_fps_for(clip.duration)
    if not (prep / "input.json").is_file():
        prep.mkdir(parents=True, exist_ok=True)
        frames = extract_frames(clip, prep, overview_fps)
        sheets = _rel_sheets(build_contact_sheets(frames, prep / "sheets"))
        dense_meta: list[dict] = []
        if unit in HIGH_RISK_DENSE_UNITS and clip.duration > DENSE_WINDOW_SEC:
            # Mid-clip handoff / desk window where anatomy misses clustered in pilot.
            mid = max(0.0, clip.duration / 2 - DENSE_WINDOW_SEC / 2)
            end = min(clip.duration, mid + DENSE_WINDOW_SEC)
            dense_dir = prep / "dense"
            dense_dir.mkdir(exist_ok=True)
            try:
                dense_frames = extract_frames(
                    clip, dense_dir, DENSE_WINDOW_FPS, start=mid, end=end
                )
                dense_sheets = _rel_sheets(
                    build_contact_sheets(
                        dense_frames, dense_dir / "sheets", prefix="D"
                    )
                )
                sheets.extend(dense_sheets)
                dense_meta.append(
                    {
                        "start": mid,
                        "end": end,
                        "fps": DENSE_WINDOW_FPS,
                        "prefix": "D",
                        "frames": len(dense_frames),
                    }
                )
            except MediaError:
                dense_meta.append({"error": "dense_window_skipped"})
        prompt_path = _JOB_PROMPT.get(unit)
        text = prompt_path.read_text(encoding="utf-8") if prompt_path and prompt_path.is_file() else ""
        entry = {
            "unit": unit,
            "layer": "L3",
            "mode": "triage",
            "source": clip.public(ROOT),
            "prompt_sha256": hashlib.sha256(text.encode()).hexdigest() if text else None,
            "overview_fps": overview_fps,
            "dense_windows": dense_meta,
            "frames": sum(len(s.get("cells") or []) for s in sheets),
            "sheets": sheets,
            "source_expectation_not_observation": text,
            "instruction": "Expectations are data, not observations. L3=triage not clear bill.",
            "false_positive_hint": FALSE_POSITIVE_HINT,
        }
        (prep / "input.json").write_text(
            json.dumps(entry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    else:
        entry = json.loads((prep / "input.json").read_text(encoding="utf-8"))
        overview_fps = float(entry.get("overview_fps") or overview_fps)

    images = [ROOT / s["path"] for s in entry["sheets"]]
    input_rel = str((prep / "input.json").relative_to(ROOT))
    attempt = work / "overview-low"
    if attempt.exists():
        result = json.loads((attempt / "result.json").read_text(encoding="utf-8"))
    else:
        result = run_cli(
            ROOT,
            attempt,
            make_prompt(unit, input_rel, images, overview_fps=overview_fps),
            images,
            model=model,
            timeout=300,
        )
    ids = {c["frame_id"] for s in entry["sheets"] for c in s["cells"]}
    answer = result.get("answer")
    hard_issues: list[str] = []
    soft_warnings: list[str] = []
    if answer:
        # Structural checks only; unknown frame ids are soft (triage nav).
        raw_issues = validate_screen_answer(answer, unit, ids)
        hard_issues = [i for i in raw_issues if i != "Model cited unknown frame IDs"]
        soft_warnings.extend(sanitize_answer_frame_ids(answer, ids))
        if "Model cited unknown frame IDs" in raw_issues:
            soft_warnings.append("unknown_frame_ids_softened")
    else:
        hard_issues = ["No answer"]

    suspects = (answer or {}).get("suspects") or []
    if not isinstance(suspects, list):
        suspects = []
        hard_issues.append("Invalid suspects: list required")
    triage_risk = score_triage(
        suspects, (answer or {}).get("triage_risk") if answer else None
    )
    if answer is not None:
        answer["triage_risk"] = triage_risk

    recorded = result.get("status") == "MODEL_SCREEN_RECORDED" and answer is not None
    if recorded and not hard_issues:
        l3_status = "SUSPECTS_OPEN" if suspects else "SCREENED_NO_SUSPECTS"
    elif recorded:
        # Answer usable for triage even with structural nits / soft id issues.
        l3_status = "TRIAGE_PARTIAL"
    else:
        l3_status = "SCREEN_INCOMPLETE"

    screen = {
        "schema": "l3_screen/v2-triage",
        "unit": unit,
        "cand": str(cand),
        "mode": "triage",
        "L3_status": l3_status,
        "triage_risk": triage_risk if recorded else "NONE",
        "model": model,
        "overview_fps": overview_fps,
        "cli_status": result.get("status"),
        "validation_issues": hard_issues,
        "soft_warnings": soft_warnings,
        "suspect_count": len(suspects),
        "answer": answer,
        "work": str(work.relative_to(ROOT)),
        "at": utc_now(),
        "note": (
            "Triage only — ranks human scan priority; not a clear bill. "
            "Unknown frame ids → soft_nav_hints. Use l3_confirm.json queue."
        ),
    }
    (cand / "l3_screen.json").write_text(
        json.dumps(screen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (work / "l3_screen.json").write_text(
        json.dumps(screen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    confirm = build_confirm(
        answer, unit, cand, triage_risk=screen["triage_risk"]
    )
    (cand / "l3_confirm.json").write_text(
        json.dumps(confirm, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (work / "l3_confirm.json").write_text(
        json.dumps(confirm, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    # Triage succeeds whenever model answered — incomplete only if no answer.
    return {
        "ok": recorded,
        "L3_status": l3_status,
        "triage_risk": screen["triage_risk"],
        "work": str(work),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cand", type=Path, required=True)
    ap.add_argument("--unit", required=True)
    ap.add_argument("--batch", default="lihun-v23-pilot-abcd-1024")
    ap.add_argument("--allow-model-upload", action="store_true")
    ap.add_argument("--model", default="grok-4.7-low",
                    choices=["grok-4.7-low", "grok-4.7-medium"])
    args = ap.parse_args()
    out = screen_cand(
        args.unit,
        args.cand.resolve(),
        args.batch,
        allow_upload=args.allow_model_upload,
        model=args.model,
    )
    print(json.dumps(out, ensure_ascii=False), flush=True)
    return 0 if out.get("ok") or out.get("skipped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
