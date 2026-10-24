# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow==12.2.0"]
# ///
"""First-three-episode calibration follow-ups, including two explicitly named legacy cases.

This helper's legacy questions/windows are specific to the current lihun fixtures.
Do not reuse those questions blindly for an unrelated batch or character set.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from comfy_orch.av_review.cli_screen import run_cli, validate_screen_answer
from comfy_orch.av_review.contact_sheets import build_contact_sheets
from comfy_orch.av_review.frames import extract_frames
from comfy_orch.av_review.media import inspect_clip


LEGACY = {"EP01-U02": ["F002", "F007", "F009"], "EP01-U04": ["F001", "F013", "F014", "F015"]}


def save(path, data):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def choose_frames(answer: dict, available: set[str], mandatory: list[str]) -> tuple[list[str], list[str]]:
    requested = list(mandatory)
    priority = {"anatomy": 0, "wardrobe_continuity": 1, "prop_continuity": 1,
                "composition_constraint": 2, "other": 2}
    suspects = sorted(answer.get("suspects", []), key=lambda item: priority.get(item.get("category"), 2))
    for suspect in suspects:
        requested.extend(suspect.get("detail_frame_ids", []) or suspect.get("frame_ids", []))
    requested.extend(answer.get("detail_frame_ids", []))
    ordered = list(dict.fromkeys(i for i in requested if isinstance(i, str) and i in available))
    return ordered[:6], ordered[6:]


def prepare_detail(directory: Path, data: dict, result: dict) -> dict:
    cells = {c["frame_id"]: c for s in data["sheets"] for c in s["cells"]}
    selected, deferred = choose_frames(result.get("answer", {}), set(cells), LEGACY.get(data["unit"], []))
    manifest = {"unit": data["unit"], "source": data["source"], "selected": [], "deferred": deferred,
                "overview_model_answer": result.get("answer"), "audio_included": False,
                "source_expectations_not_observations": data["source_expectation_not_observation"],
                "legacy_question_not_independent_blind_test": data["unit"] in LEGACY}
    if selected:
        clip = inspect_clip(ROOT, data["source"]["path"])
        if clip.sha256 != data["source"]["sha256"]:
            raise ValueError("Detail source differs from overview source")
        frames = extract_frames(clip, directory, 1, native_resolution=True)
        for index, frame_id in enumerate(selected):
            frame = frames[int(frame_id[1:])-1]
            if abs(frame.time-cells[frame_id]["source_time"]) > 0.001:
                raise ValueError("Native detail frame time differs from overview")
            manifest["selected"].append({"frame_id": frame_id, "time": frame.time,
                                         "path": str(frame.path.relative_to(ROOT)), "sha256": frame.sha256})
        if data["unit"] == "EP01-U02":
            dense_root = directory / "dense-coat-window"
            dense_root.mkdir()
            dense = extract_frames(clip, dense_root, 4, start=5.5, end=8.5, native_resolution=True)
            sheets = build_contact_sheets(dense, dense_root / "sheets", prefix="D")
            for sheet in sheets:
                sheet["path"] = str(Path(sheet["path"]).relative_to(ROOT))
                for cell in sheet["cells"]:
                    cell["frame_path"] = str(Path(cell["frame_path"]).relative_to(ROOT))
            manifest["dense_navigation"] = {"source_window": [5.5, 8.5], "fps": 4, "sheets": sheets}
    save(directory / "input.json", manifest)
    return manifest


def detail_prompt(input_path: Path, data: dict) -> str:
    listed = [item["path"] for item in data["selected"]]
    listed.extend(s["path"] for s in data.get("dense_navigation", {}).get("sheets", []))
    images = "\n".join(listed)
    return f"""Read-only original-still follow-up for {data['unit']}. Read {input_path.relative_to(ROOT)},
then use Read to view ALL listed original stills and any explicitly annotated D-prefix dense navigation sheets:
{images}
Only Read; no shell, browser, search, MCP or other files. Do not modify anything.
The prior model answer is a hypothesis, NOT ground truth. Independently compare actual full-frame details.
If this is EP01-U02, additionally describe whether the red coat is worn, held, or off-screen at each selected time.
If dense D-prefix cells are present, use their source-relative times to describe the coat transfer from 5.5-8.5s.
Dense sheets are thumbnails, not full-resolution evidence or continuous playback.
If this is EP01-U04, additionally describe who is visible in the final group shot; names remain tentative.
For EP01-U04 the source final-shot line explicitly says 'Damian在镜头外'. Check the older dark-suit man's
presence using opening and final originals; do not treat this question as proof of a violation.
Reflection and two ordinary overlapping hands may explain suspects. Do not declare an extra finger if hidden.
Separate visible anomalies from source-execution deviations and insufficient evidence. A cropped or tiny ring,
garment, screen text, or hand is not proof it is absent or malformed. Check explicit removed-coat/offscreen/transfer
constraints separately rather than merely repeating the overview's list. Unseen intervals stay unverified.
You have NO AUDIO and only stills: cannot verify voice, lip sync, simultaneous speech or continuous actions.
Return ONLY JSON: {{"unit":"{data['unit']}","audio_status":"AUDIO_UNAVAILABLE","L2_status":"NOT_DONE",
"frame_observations":[{{"frame_id":"F001","observed":""}}],
"suspect_updates":[{{"id":"S1","status":"SUPPORTED_STILL_SUSPECT|NOT_SUPPORTED_IN_SELECTED_STILLS|UNVERIFIABLE",
"issue_class":"VISUAL_ANOMALY|SOURCE_DEVIATION|INSUFFICIENT_EVIDENCE",
"frame_ids":[],"reason":"","alternative_explanation":""}}],"constraint_checks":[],"limitations":[]}}.
No update counts as human clearance or confirmed defect. Do not invent evidence from the prior hypothesis.
"""


def process(batch_root: Path, entry: dict, overview_dir: str, model: str):
    unit_root = batch_root / entry["unit"]
    output = unit_root / "detail-prepared"
    if output.exists():
        print(entry["unit"]+" DETAIL_SKIPPED_EXISTING_ATTEMPT", flush=True)
        prior = unit_root / "detail/result.json"
        return prior.exists() and json.loads(prior.read_text())["status"] == "MODEL_SCREEN_RECORDED"
    data = json.loads((ROOT / entry["input"]).read_text())
    overview = json.loads((unit_root / overview_dir / "result.json").read_text())
    output.mkdir()
    ids = {c["frame_id"] for s in data["sheets"] for c in s["cells"]}
    if overview.get("answer") and validate_screen_answer(overview["answer"], entry["unit"], ids):
        save(output / "not-run.json", {"status": "INVALID_OVERVIEW_SCHEMA", "unit": entry["unit"]})
        return False
    if overview["status"] != "MODEL_SCREEN_RECORDED" and entry["unit"] not in LEGACY:
        save(output / "not-run.json", {"status": "OVERVIEW_INCOMPLETE", "unit": entry["unit"]})
        return False
    prepared = prepare_detail(output, data, overview)
    if not prepared["selected"]:
        save(output / "not-run.json", {"status": "NO_DETAIL_REQUESTED_NOT_CLEARED", "unit": entry["unit"]})
        print(entry["unit"]+" NO_DETAIL_REQUESTED", flush=True)
        return True
    images = [ROOT / f["path"] for f in prepared["selected"]]
    images.extend(ROOT / s["path"] for s in prepared.get("dense_navigation", {}).get("sheets", []))
    image_records = prepared["selected"] + prepared.get("dense_navigation", {}).get("sheets", [])
    for frame, path in zip(image_records, images):
        if hashlib.sha256(path.read_bytes()).hexdigest() != frame["sha256"]:
            raise ValueError("Native image changed before request")
    report = run_cli(ROOT, unit_root / "detail", detail_prompt(output / "input.json", prepared), images, model=model)
    print(f"{entry['unit']} DETAIL {report['status']} {report['elapsed_seconds']}s", flush=True)
    return report["status"] == "MODEL_SCREEN_RECORDED"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", required=True)
    parser.add_argument("--allow-model-upload", action="store_true")
    parser.add_argument("--overview-dir", choices=["overview", "overview-low"], default="overview")
    parser.add_argument("--model", choices=["grok-4.7-low", "grok-4.7-medium"], default="grok-4.7-low")
    args = parser.parse_args()
    if not args.allow_model_upload:
        raise SystemExit("Explicit --allow-model-upload is required")
    path = ROOT / args.batch
    batch = json.loads((path / "batch.json").read_text())
    failures = 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        for start in range(0, len(batch["units"]), 2):
            results = list(pool.map(lambda entry: process(path, entry, args.overview_dir, args.model),
                                    batch["units"][start:start+2]))
            failures += sum(not result for result in results)
            if failures >= 2:
                print("DETAIL_CIRCUIT_OPEN: two unsuccessful attempts; remaining units not submitted", flush=True)
                break


if __name__ == "__main__":
    main()
