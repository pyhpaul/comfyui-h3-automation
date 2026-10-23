#!/usr/bin/env python3
"""Prepare this explicitly selected v21 EP01 pilot, not automatic editorial decisions."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


HASHES = [
    "d203606e77878b5bf4e29fd641dbf587db0a8cf56cc375b865d7fe86c791661a",
    "e6a1b4ac7c001abab9ea7e9ea7a37a638697a1fd2e87901e00631a2a6f00c699",
    "33235d473fdc50b9aa38e022add5489116c83aa4e848934de3d4809730c76709",
    "54ebc96b6aa86521d9663563866a41f625f94362bcba7ab2208c1bbceb2776c8",
]
ENDS = [342, 340, 228, 330]
REASONS = [
    "Keep ring action, all three speeches and entrance reaction; remove 20 trailing frames.",
    "Keep full unit: first word starts at zero and final question ends near source end.",
    "Keep first complete scripted exchange plus 0.87s reaction; omit repeated/ad-lib tail candidates. Human listening review required.",
    "Keep both speeches, shoe-tying action and final reaction; remove 10 trailing frames; last six frames fade into end signature.",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="original project root containing the task cache")
    parser.add_argument("--revision", choices=["v1", "v2"], default="v1")
    args = parser.parse_args()
    root = args.root.resolve()
    cache = root / ".cache/ep_post_pilot_v1"
    cache.mkdir(parents=True, exist_ok=True)
    assets = root / "assets/episode_post/local/pilots/lihun-v21-ep01"
    sources = {}
    clips = []
    for i in range(1, 5):
        unit = f"U{i:02d}"
        folder = assets / "units" / f"{unit}-WENXI"
        source = folder / f"EP01-{unit}-lihun-wenxi_00001-audio.mp4"
        prompt = folder / "prompt_h3.txt"
        if sha(source) != HASHES[i - 1]:
            raise ValueError(f"unrecognized pilot source: {source}")
        sources[unit] = {
            "path": str(source), "sha256": HASHES[i - 1],
            "prompt": str(prompt), "prompt_sha256": sha(prompt),
            "meta": str(folder / "run_meta.json"),
            "analysis": str(assets / "analysis" / f"{unit}-WENXI.json"),
            "archive_unit": f"EP01/{unit}-WENXI",
        }
        clips.append({"unit": unit, "in_frame": 0, "out_frame": ENDS[i - 1],
                      "reason": REASONS[i - 1]})
    music = assets / "music/sb_undertow.mp3"
    manifest = {
        "schema": "ep-post-pilot/v1", "episode": "EP01", "source_version": "lihun-v21",
        "source_batch": "离婚后，我成了前夫的继母（10.21）",
        "status": "PILOT_REQUIRES_FULL_WATCH", "fps": 24, "width": 768, "height": 1376,
        "sources": sources, "clips": clips, "endcard_frames": 30,
        "subtitle_language": "en", "subtitle_aliases": {"damien": "damian"},
        "audio": {"dialogue_stage_lufs": -18, "final_lufs": -16, "true_peak_target": -1.5},
        "music": {"path": str(music), "sha256": sha(music),
                  "source_url": "https://www.scottbuckley.com.au/library/undertow/",
                  "download_url": "https://www.scottbuckley.com.au/library/wp-content/uploads/2019/12/sb_undertow.mp3",
                  "license_url": "https://creativecommons.org/licenses/by/4.0/",
                  "usage_url": "https://www.scottbuckley.com.au/library/using-this-music/",
                  "credit": "'Undertow' by Scott Buckley - released under CC-BY 4.0. www.scottbuckley.com.au",
                  "adaptation": "Excerpts, fades, level changes and dialogue ducking.",
                  "target_lufs_before_duck": -29,
                  "cues": [{"start": 21.0, "end": 32.0, "source_in": 0,
                            "reason": "Brother/father relationship reveal, through marriage declaration."},
                           {"start": 44.0, "end": 1270 / 24, "source_in": 57,
                            "reason": "Quiet shoe-tying contrast, final reaction and end signature."}]},
        "review_notes": [
            "All source clips retain native geometry; no upscaling, synthetic B-roll or regenerated faces.",
            "U03 trim avoids candidate repeat/garble but omits its final reaction shot; U04 supplies the next reaction. Narrative review required.",
            "Source wardrobe, geography and mouth-owner correctness are not repaired or certified.",
            "Shot contact sheets and ASR do not replace full audio/video viewing.",
        ],
    }
    manifest["revision"] = args.revision
    if args.revision == "v2":
        manifest["subtitle_style"] = {
            "font_size": 38, "outline": 2,
            "end_overrides": {"You don't need an audience.": 9.65,
                              "He's your brother, Ethan.": 22.65,
                              "We married yesterday.": 31.85,
                              "Mine.": 20.70, "Yes.": 40.30},
            "line_breaks": {"You're bringing strangers into our home?":
                            "You're bringing strangers\ninto our home?"},
        }
        manifest["change_notes"] = [
            "Materialize sample-accurate music cue tracks and mix offline with dialogue-driven smooth ducking.",
            "Require actual music residuals to match the scheduled cue windows, including the ending.",
            "Extend five reviewed subtitle endings, trial 38px/2px style and one semantic line break.",
            "Retain v1 story cuts, shoe-tying action, six-frame picture fade and 30-frame end signature.",
        ]
    target = cache / ("pilot_input_v2.json" if args.revision == "v2" else "pilot_input.json")
    with target.open("x") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(target)


if __name__ == "__main__":
    main()
