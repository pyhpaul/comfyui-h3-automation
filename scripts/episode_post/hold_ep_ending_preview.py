#!/usr/bin/env python3
"""Add one second of intentional peak-effect hold before the concept end card."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from ep_pilot_media import probe, run_logged
from ep_pilot_timeline import verify_source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    source = root / "assets/episode_post/local/endings/bloom-hold-suspense/v1/base-bloom.mp4"
    verify_source(source, "a884fd838940f24c584927f1d13baca8d65842146693e7e0a356fef54ec5366a")
    out = root / "outputs/ep-post-pilot/EP01-v21-reference-bloom-hold1s-preview"
    out.mkdir(parents=True, exist_ok=False)
    target = out / "EP01-ending-bloom-hold1s-preview.mp4"
    # Add exactly 24 frozen frames before the card; do not freeze any dialogue.
    # Preserve the first 3s of sound; stretch only the music tail without pitch shift.
    graph = (
        "[0:v]split=2[t][c];"
        "[t]trim=end_frame=90,setpts=PTS-STARTPTS,tpad=stop=24:stop_mode=clone[hold];"
        "[c]trim=start_frame=90:end_frame=120,setpts=PTS-STARTPTS[card];"
        "[hold][card]concat=n=2:v=1:a=0[v];"
        "[0:a]asplit=2[a0][a1];"
        "[a0]atrim=end=3,asetpts=PTS-STARTPTS[head];"
        "[a1]atrim=start=3:end=5,asetpts=PTS-STARTPTS,atempo=0.6666666667,"
        "apad,atrim=duration=3[tail];"
        "[head][tail]concat=n=2:v=0:a=1[a]"
    )
    run_logged([
        "ffmpeg", "-nostdin", "-v", "error", "-n", "-i", str(source),
        "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(target),
    ], out / "logs/render.log")
    data = probe(target, out / "logs/probe.log")
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    audio = next(s for s in data["streams"] if s["codec_type"] == "audio")
    if int(video["nb_frames"]) != 144 or abs(float(video["duration"]) - 6) > 1e-5:
        raise ValueError("one-second hold frame count mismatch")
    if abs(float(video["duration"]) - float(audio["duration"])) > 1 / 24:
        raise ValueError("hold preview AV duration mismatch")
    run_logged(["ffmpeg", "-v", "error", "-i", str(target), "-f", "null", "-"], out / "logs/decode.log")
    report = {
        "status": "TECHNICAL_PASS_VISUAL_REVIEW_PENDING", "file": target.name,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "frames": 144, "seconds": 6, "added_hold_frames": 24,
        "hold_start_s": 3.75, "hold_end_s": 4.75, "card_start_s": 4.75,
        "audio": "First 3 seconds preserved in timing; last 2 seconds stretched to 3 without pitch shift.",
        "scope": "concept ending preview only; not a new full episode",
        "filter_graph": graph,
    }
    (out / "preview_manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"out": str(out), "sha256": report["sha256"], "frames": 144}))


if __name__ == "__main__":
    main()
