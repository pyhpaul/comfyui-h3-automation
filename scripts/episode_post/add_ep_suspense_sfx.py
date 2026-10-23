#!/usr/bin/env python3
"""Add locally synthesized suspense sound to the six-second held ending preview."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from ep_pilot_audio_qc import check_music_timing, decode_stereo
from ep_pilot_media import loudness, probe, run_logged
from ep_pilot_mix import mix_pcm_tracks
from ep_pilot_timeline import verify_source


def render_stems(out: Path) -> list[Path]:
    recipes = [
        ("air-rise", "anoisesrc=color=pink:amplitude=0.15:r=48000:d=1.3:seed=20261022",
         "highpass=f=650,lowpass=f=3600,afade=t=in:d=1.1,afade=t=out:st=1.1:d=0.2", 2450),
        ("low-impact", "aevalsrc=0.1*sin(2*PI*(65*t-7*t*t))*exp(-3*t)+0.035*sin(2*PI*130*t)*exp(-4*t):s=48000:d=1.4",
         "highpass=f=35,lowpass=f=220,afade=t=in:d=0.015,afade=t=out:st=1.1:d=0.3", 3750),
    ]
    stems = []
    for name, generator, shaping, delay in recipes:
        dest = out / f"{name}.wav"
        run_logged([
            "ffmpeg", "-nostdin", "-v", "error", "-n", "-f", "lavfi", "-i", generator,
            "-af", shaping + f",aformat=channel_layouts=stereo,adelay={delay}:all=1,"
            "asetpts=N/SR/TB,apad,atrim=duration=6,asetpts=N/SR/TB",
            "-ar", "48000", "-ac", "2", "-c:a", "pcm_f32le", str(dest),
        ], out / "logs" / f"{name}.log")
        stems.append(dest)
    return stems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    source = root / "outputs/ep-post-pilot/EP01-v21-reference-bloom-hold1s-preview/EP01-ending-bloom-hold1s-preview.mp4"
    verify_source(source, "67013e1678d6ce217155f06d8c1e3ee57bd5a716542d2b6b832f2ff2ed3952cf")
    out = root / "outputs/ep-post-pilot/EP01-v21-reference-bloom-hold1s-suspense-final"
    out.mkdir(parents=True, exist_ok=False)
    stems = render_stems(out)
    dry = out / "dry.wav"
    # AAC decoding includes trailing codec padding; canonicalize the six-second PCM timeline.
    run_logged([
        "ffmpeg", "-nostdin", "-v", "error", "-n", "-i", str(source), "-vn", "-af",
        "aresample=48000,atrim=end_sample=288000,asetpts=N/SR/TB",
        "-ac", "2", "-c:a", "pcm_s24le", str(dry),
    ], out / "logs/dry.log")
    raw = decode_stereo(dry)
    summed = raw + sum(decode_stereo(path) for path in stems)
    if float(np.max(np.abs(summed))) >= 1:
        raise ValueError("suspense mix would clip PCM before peak limiting")
    mix = out / "mix.wav"
    mix_pcm_tracks(dry, stems, mix, 6, [], out / "logs/mix.log")
    timing = check_music_timing(dry, mix, [
        {"start": 2.45, "end": 3.75}, {"start": 3.75, "end": 5.15}], 6)
    timing["scope"] = "pre-limiter SFX residual versus canonical PCM, not subjective listening"
    timing["tail_sfx_rms"] = timing.pop("tail_music_rms")
    target = out / "EP01-ending-hold1s-suspense.mp4"
    run_logged([
        "ffmpeg", "-nostdin", "-v", "error", "-n", "-i", str(source), "-i", str(mix),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-af",
        "alimiter=limit=0.8:level=0:latency=1", "-c:a", "aac", "-b:a", "192k",
        "-ar", "48000", "-movflags", "+faststart", str(target),
    ], out / "logs/export.log")
    data = probe(target, out / "logs/probe.log")
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    audio = next(s for s in data["streams"] if s["codec_type"] == "audio")
    if int(video["nb_frames"]) != 144 or abs(float(video["duration"]) - float(audio["duration"])) > 1 / 24:
        raise ValueError("suspense preview frame/AV duration mismatch")
    levels = loudness(target, out / "logs/loudness.log")
    if float(levels["input_tp"]) > -1:
        raise ValueError(f"suspense preview exceeds trial peak ceiling: {levels}")
    run_logged(["ffmpeg", "-v", "error", "-i", str(target), "-f", "null", "-"], out / "logs/decode.log")
    report = {
        "status": "TECHNICAL_PASS_REVIEW_PENDING", "file": target.name,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "frames": 144, "seconds": 6, "hold_start_s": 3.75, "card_start_s": 4.75,
        "sfx": [{"kind": "filtered air rise", "start": 2.45, "end": 3.75},
                {"kind": "decaying low-frequency impact", "start": 3.75, "end": 5.15}],
        "sfx_provenance": "Locally synthesized deterministic noise and sine waveforms; no external samples or paid generation.",
        "sfx_timing": timing, "loudness": levels,
        "limiter": "0.8FS, no makeup gain, latency compensated",
        "scope": "six-second concept only; original and previous revisions preserved; no real-time listening claimed",
    }
    (out / "preview_manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"out": str(out), "sha256": report["sha256"], "true_peak": levels["input_tp"]}))


if __name__ == "__main__":
    main()
