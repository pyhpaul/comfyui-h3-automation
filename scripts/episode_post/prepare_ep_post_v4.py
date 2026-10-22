#!/usr/bin/env python3
"""Apply user feedback: clean end card and visibly stronger ending push."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from ep_pilot_creative import ending_video_filter
from ep_pilot_timeline import verify_source


def build(config: dict) -> dict:
    for source in config["sources"].values():
        verify_source(Path(source["path"]), source["sha256"])
    config["revision"] = "v4-visible-ending"
    config["ending_push"] = {"start_frame": 276, "end_frame": 324,
                             "zoom": 1.10, "anchor_x": 0.60, "anchor_y": 0.42}
    ending_video_filter(config["ending_push"], 330)
    config["endcard"] = {"show_music_credit": False,
                         "credit_delivery": "MUSIC_CREDITS.txt plus publication description and MP4 metadata"}
    plan = config["creative_plan"]
    plan["revision"] = config["revision"]
    plan["execution_status"] = "PLANNED"
    plan["perceptual_review"] = "NOT_DONE"
    plan["ending"].update({
        "global_start_s": 49.4166666667, "push": config["ending_push"],
        "reason": "User found v3 too subtle: visible 10 percent smooth push over two seconds, then existing fade and clean card.",
        "endcard": config["endcard"],
    })
    plan["user_feedback"] = "Remove music credit text from end card; make ending animation clearly visible."
    plan["risks"] = ["Stronger push requires actual face, hand and crop checks.",
                     "Music attribution remains required in the accompanying credits and publication description.",
                     "No real-time listening or full-watch certification."]
    config["change_notes"] = [
        "Remove both small music credit lines from end card; retain full attribution outside the picture.",
        "Replace 3.5 percent / 1.25 second push with 10 percent / 2 second smooth push at 49.416667-51.416667s.",
        "Keep all story frames, dialogue, English captions and music settings identical to v3."]
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    source = root / ".cache/ep_post_pilot_v3/pilot_input_v3.json"
    cache = root / ".cache/ep_post_pilot_v4"
    cache.mkdir(exist_ok=False)
    config = build(json.loads(source.read_text()))
    config["parent_input_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    dest = cache / "pilot_input_v4.json"
    with dest.open("x") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(dest)


if __name__ == "__main__":
    main()
