#!/usr/bin/env python3
"""Render a short reference-directed bloom ending, not a full episode revision."""
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
    manifest = json.loads((root / ".cache/ep_post_pilot_v4/pilot_input_v4.json").read_text())
    source = manifest["sources"]["U04"]
    verify_source(Path(source["path"]), source["sha256"])
    previous = root / "outputs/ep-post-pilot/EP01-v21-v4-visible-ending"
    out = root / "outputs/ep-post-pilot/EP01-v21-reference-bloom-preview"
    out.mkdir(parents=True, exist_ok=False)
    logs = out / "logs"
    # Screen a blurred highlight layer over the image, then ramp toward soft focus.
    weight = "min(max((T-2.5)/0.6,0),1)"
    highlights = ":".join(f"{ch}='clip((val-135)*2.2,0,255)'" for ch in "rgb")
    graph = (
        "[0:v]trim=start_frame=240:end_frame=330,setpts=PTS-STARTPTS,"
        "format=gbrp,split=3[clear][body][light];"
        f"[light]lutrgb={highlights},gblur=sigma=12[glow];"
        "[body][glow]blend=all_mode=screen,gblur=sigma=6,eq=brightness=0.08[soft];"
        f"[clear][soft]blend=all_expr='A*(1-({weight}))+B*({weight})',format=yuv420p[tail];"
        "[1:v]setpts=PTS-STARTPTS,format=yuv420p[card];"
        "[tail][card]concat=n=2:v=1:a=0[v];"
        "[2:a]atrim=start=47.9166666667:end=52.9166666667,asetpts=PTS-STARTPTS[a]"
    )
    target = out / "EP01-ending-bloom-preview.mp4"
    run_logged([
        "ffmpeg", "-nostdin", "-v", "error", "-n", "-i", source["path"],
        "-i", str(previous / "work/endcard.mkv"),
        "-i", str(previous / "EP01-review-en.mp4"), "-filter_complex", graph,
        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "fast",
        "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-ar", "48000", "-movflags", "+faststart", str(target),
    ], logs / "render.log")
    data = probe(target, logs / "probe.log")
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    audio = next(s for s in data["streams"] if s["codec_type"] == "audio")
    if int(video["nb_frames"]) != 120 or abs(float(video["duration"]) - float(audio["duration"])) > 1 / 24:
        raise ValueError("ending preview frame or AV duration mismatch")
    run_logged(["ffmpeg", "-v", "error", "-i", str(target), "-f", "null", "-"], logs / "decode.log")
    report = {
        "status": "TECHNICAL_PASS_VISUAL_REVIEW_PENDING", "file": target.name,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "frames": 120,
        "seconds": 5, "effect_start_s": 2.5, "effect_full_s": 3.1, "card_start_s": 3.75,
        "effect": "animated highlight bloom and soft focus, not a zoom or identity change",
        "audio": "unchanged scoring design from v4, excerpt re-encoded for this preview; no new SFX",
        "reference": "User-provided 2026-10-22 screen recording; not redistributed",
        "scope": "ending-only concept preview; not a full episode release or a subjective listening approval",
        "filter_graph": graph,
    }
    (out / "preview_manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"out": str(out), "sha256": report["sha256"], "frames": 120}))


if __name__ == "__main__":
    main()
