#!/usr/bin/env python3
"""Prepare the agent-directed EP01 v3 using existing hash-locked pilot assets."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from ep_pilot_media import loudness
from ep_pilot_creative import ending_video_filter, validate_protected_ranges
from ep_pilot_timeline import Clip, verify_source


def choose_music(config: dict, logs: Path) -> list[dict]:
    path = Path(config["music"]["path"])
    whole = loudness(path, logs / "whole-music.log")
    base_gain = config["music"]["target_lufs_before_duck"] - float(whole["input_i"])
    sections = [
        {"start": 20.75, "end": 32.25, "source_in": 0, "target": -30.5,
         "fade_in": 0.7, "fade_out": 0.9,
         "reason": "Family and marriage reveal; enter after Mine, then withdraw before direct confrontation."},
        {"start": 42.5, "end": 1270 / 24, "source_in": 57, "target": -29,
         "fade_in": 1.0, "fade_out": 1.0,
         "reason": "After the last spoken response, support shoe tying and the silent power reversal through the end card."},
    ]
    for i, cue in enumerate(sections):
        measured = loudness(path, logs / f"excerpt-{i}.log",
                            cue["source_in"], cue["end"] - cue["start"])
        gain = round(cue.pop("target") - float(measured["input_i"]), 3)
        cue["measured_excerpt_lufs"] = float(measured["input_i"])
        cue["gain_before_duck_db"] = gain
        cue["gain_offset_db"] = round(gain - base_gain, 3)
    return sections


def build(config: dict, logs: Path) -> dict:
    for source in config["sources"].values():
        verify_source(Path(source["path"]), source["sha256"])
        verify_source(Path(source["prompt"]), source["prompt_sha256"])
    verify_source(Path(config["music"]["path"]), config["music"]["sha256"])
    config["revision"] = "v3-agent-directed"
    config["ending_push"] = {"start_frame": 294, "end_frame": 324,
                             "zoom": 1.035, "anchor_x": 0.60, "anchor_y": 0.42}
    ending_video_filter(config["ending_push"], 330)
    config["protected_ranges"] = [
        {"unit": "U04", "in_frame": 100, "out_frame": 330,
         "reason": "Protect silent reaction, shoe tying, rising, handhold and final confrontation."}]
    validate_protected_ranges(config["protected_ranges"], [Clip(c["unit"], c["in_frame"], c["out_frame"])
                                                          for c in config["clips"]])
    config["music"]["cues"] = choose_music(config, logs)
    config["subtitle_style"]["end_overrides"].update({
        "You don't need an audience.": 9.54, "We married yesterday.": 31.50})
    config["creative_plan"] = {
        "schema": "ep-agent-direction/v1", "episode": "EP01", "revision": config["revision"],
        "execution_status": "PLANNED", "perceptual_review": "NOT_DONE",
        "goal": "Quiet retaliation: she chooses the child while he remains speechless.",
        "basis": "Actual source/v2 frames, script and audio signal analysis; no real-time listening claimed.",
        "beats": [{"start": 0, "end": 20.75, "mood": "exposed confrontation", "music": "none"},
                  {"start": 20.75, "end": 32.25, "mood": "family and marriage revelation", "music": "Undertow opening"},
                  {"start": 32.25, "end": 42.5, "mood": "direct challenge and calm response", "music": "none"},
                  {"start": 42.5, "end": 1270 / 24, "mood": "child care, power reversal and unresolved ending", "music": "Undertow later passage"}],
        "ending": {"source_unit": "U04", "global_start_s": 50.1666666667,
                   "push": config["ending_push"], "picture_fade_frames": 6, "card_frames": 30,
                   "reason": "Subtle smooth push preserves both characters and intensifies the silent confrontation."},
        "music": config["music"]["cues"], "music_asset_sha256": config["music"]["sha256"],
        "rejected": ["Ghosting would read as a generation defect rather than quiet retaliation.",
                     "No extra tonal hit: existing music has low-frequency energy; no listening evidence supports stacking another pitch.",
                     "No unrelated second track merely to create variety; two contrasting passages maintain thematic identity."],
        "user_adjustable": ["Ending push strength or removal", "Cue entry, excerpt choice and level", "Ending fade and card duration"],
        "risks": ["Opening cue is stronger than v2; requires real listening before publication.",
                  "Push can expose existing source defects; dense-frame inspection required.",
                  "No generated faces, dialogue replacement, frozen ending or synthetic bridge."],
    }
    config["change_notes"] = [
        "Agent-directed ending: smooth 3.5 percent push across local frames 294-324, retaining every story frame.",
        "Two separately measured music passages with explicit fades, levels and narrative roles.",
        "Protect U04 nonverbal story action and snap two subtitle ends to reviewed cuts.",
        "No added SFX or ghosting; conservative choices documented in creative plan."]
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    cache = root / ".cache/ep_post_pilot_v3"
    cache.mkdir(exist_ok=False)
    original = root / ".cache/ep_post_pilot_v1/pilot_input_v2.json"
    config = build(json.loads(original.read_text()), cache / "logs")
    config["parent_input_sha256"] = hashlib.sha256(original.read_bytes()).hexdigest()
    target = cache / "pilot_input_v3.json"
    with target.open("x") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(target)


if __name__ == "__main__":
    main()
