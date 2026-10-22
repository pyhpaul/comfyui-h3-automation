#!/usr/bin/env python3
"""Render one EP01 agent decision plan against hash-locked shared comparison inputs."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import numpy as np

from ep_pilot_media import (concatenate, export_video, loudness, mix_music, normalize_audio,
                            render_endcard, render_segment)
from ep_pilot_audio_qc import check_music_timing, decode_stereo
from ep_pilot_mix import mix_pcm_tracks
from ep_pilot_creative import validate_protected_ranges
from ep_pilot_timeline import Clip, validate_clips, verify_source
from episode_ending import ending_layout, render_bloom_segment, render_sfx
from run_ep_post_pilot import collect_captions, write_subtitles, validate_sources, check_output, save


def load_config(root: Path, shared: dict, plan: dict) -> dict:
    if plan["ending"]["preset_id"] != "bloom-hold-suspense" or plan["ending"]["preset_version"] != 1:
        raise ValueError("this renderer currently supports only bloom-hold-suspense v1")
    for item in shared["skill_snapshot"]:
        verify_source(root / item["path"], item["sha256"])
    if any("path" in cue for cue in plan["music"]["cues"]):
        raise ValueError("comparison cue cannot introduce assets outside the shared pool")
    config = {**plan, "episode": shared["episode"], "source_version": shared["source_version"],
              **{k: shared["delivery"][k] for k in ("fps", "width", "height")}}
    sources = {}
    for unit, data in shared["sources"].items():
        source = dict(data)
        for key in ("path", "prompt", "meta", "analysis"):
            source[key] = str(root / data[key])
        verify_source(Path(source["analysis"]), source["analysis_sha256"])
        verify_source(Path(source["meta"]), source["meta_sha256"])
        sources[unit] = source
    config["sources"] = sources
    music = dict(plan["music"])
    music["path"] = str(root / shared["available_music"][0]["path"])
    music["sha256"] = shared["available_music"][0]["sha256"]
    config["music"] = music
    preset_info = shared["available_presets"][0]
    verify_source(root / preset_info["path"], preset_info["sha256"])
    return config


def render_picture(config: dict, preset: dict, clips: list[Clip], out: Path) -> tuple[Path, list[dict], dict]:
    parts, stages = [], []
    for i, clip in enumerate(clips):
        source = Path(config["sources"][clip.unit]["path"])
        duration = (clip.out_frame - clip.in_frame) / 24
        level = loudness(source, out / "logs" / f"level-{i}.log", clip.in_frame / 24, duration)
        gain = round(max(-6, min(6, -18 - float(level["input_i"]))), 3)
        part = out / "work" / f"part-{i}.mkv"
        if i == len(clips) - 1:
            render_bloom_segment(source, part, clip, gain, preset, out / "logs/ending.log")
        else:
            render_segment(source, part, clip.in_frame, clip.out_frame, gain, False,
                           out / "logs" / f"part-{i}.log")
        parts.append(part)
        stages.append({"unit": clip.unit, "input_lufs": level["input_i"], "gain_db": gain})
    layout = ending_layout(sum(c.out_frame - c.in_frame for c in clips), preset)
    card = out / "work/endcard.mkv"
    render_endcard(card, layout["card_frames"], out / "logs/card.log", False)
    picture = out / "work/picture.mkv"
    concatenate(parts + [card], picture, out / "logs/concat.log", layout["total_frames"])
    return picture, stages, layout


def render_audio(config: dict, preset: dict, picture: Path, layout: dict, cues: list, out: Path) -> tuple[Path, dict]:
    total = layout["total_frames"] / 24
    music = config["music"]
    for i, cue in enumerate(music["cues"]):
        level = loudness(Path(music["path"]), out / "logs" / f"music-{i}.log",
                         cue["source_in"], cue["end"] - cue["start"])
        cue["gain_offset_db"] = cue["target_lufs_before_duck"] - float(level["input_i"])
        cue["measured_excerpt_lufs"] = float(level["input_i"])
    bed = out / "work/music-mix.wav"
    mix_music(picture, Path(music["path"]), music["cues"], bed, 0, total,
              out / "logs/music-mix.log", [(c.start, c.end) for c in cues])
    music_qc = check_music_timing(picture, bed, music["cues"], total)
    save(out / "music_timing_qc.json", music_qc)
    stems, sound_cues = render_sfx(preset, layout, out, config["ending"]["sfx_gain_db"])
    bed_samples = decode_stereo(bed)
    combined = bed_samples + sum(decode_stereo(path) for path in stems)
    if np.max(np.abs(combined)) >= 1:
        raise ValueError("pre-normalization soundtrack would clip PCM")
    mix = out / "work/mix.wav"
    mix_pcm_tracks(bed, stems, mix, total, [], out / "logs/sfx-mix.log")
    sound_qc = check_music_timing(bed, mix, sound_cues, total)
    sound_qc["scope"] = "SFX residual before whole-episode normalization"
    save(out / "sfx_timing_qc.json", sound_qc)
    normalized = out / "work/normalized.wav"
    measurement = loudness(mix, out / "logs/final-first-pass.log", true_peak_target=-2.0)
    normalize_audio(mix, normalized, measurement, out / "logs/final-second-pass.log", true_peak_target=-2.0)
    return normalized, {"music": music_qc, "sfx": sound_qc, "sfx_cues": sound_cues}


def render(root: Path, shared_file: Path, plan_file: Path, out: Path) -> None:
    shared = json.loads(shared_file.read_text())
    plan = json.loads(plan_file.read_text())
    verify_source(shared_file, plan["shared_input_sha256"])
    config = load_config(root, shared, plan)
    engine_names = ["run_episode_comparison.py", "episode_ending.py", "ep_pilot_media.py",
                    "ep_pilot_mix.py", "ep_pilot_audio_qc.py", "ep_pilot_timeline.py",
                    "ep_pilot_creative.py", "run_ep_post_pilot.py"]
    config["engine_snapshot"] = {name: hashlib.sha256((root / "scripts/episode_post" / name).read_bytes()).hexdigest()
                                 for name in engine_names}
    preset = json.loads((root / shared["available_presets"][0]["path"]).read_text())
    out.mkdir(parents=True, exist_ok=False)
    (out / "work").mkdir()
    probes = validate_sources(config, out / "logs")
    clips = [Clip(c["unit"], c["in_frame"], c["out_frame"]) for c in config["clips"]]
    selected_order = list(dict.fromkeys(c.unit for c in clips))
    if selected_order != shared["unit_order"]:
        raise ValueError("agent plan changes required unit order or omits a unit")
    ranks = [shared["unit_order"].index(c.unit) for c in clips]
    if ranks != sorted(ranks):
        raise ValueError("agent plan jumps backward between units")
    frames = {u: int(next(s for s in p["streams"] if s["codec_type"] == "video")["nb_frames"])
              for u, p in probes.items()}
    validate_clips(clips, frames)
    validate_protected_ranges(config["protected_ranges"], clips)
    captions, words = collect_captions(config, clips)
    displayed = write_subtitles(out, captions, words, config["subtitle_style"],
                                config["episode"])
    layout = ending_layout(sum(c.out_frame - c.in_frame for c in clips), preset)
    if max(c.end for c in captions) >= layout["bloom_start_s"]:
        raise ValueError("ending effect would overlap dialogue")
    save(out / "input_contract.json", shared)
    save(out / "creative_plan.json", plan)
    picture, staging, layout = render_picture(config, preset, clips, out)
    normalized, audio_qc = render_audio(config, preset, picture, layout, captions, out)
    outputs = []
    episode = config["episode"]
    for name, ass in ((f"{episode}-master.mp4", None),
                      (f"{episode}-review-en.mp4", out / f"{episode}.en.ass")):
        path = out / name
        export_video(picture, normalized, path, out / "logs" / f"export-{name}.log", ass)
        result = check_output(path, layout["total_frames"], out / "logs")
        if float(result["loudness"]["input_tp"]) > shared["delivery"]["true_peak_ceiling"]:
            raise ValueError("final encoded peak exceeds the shared comparison ceiling")
        outputs.append(result)
    validate_sources(config, out / "logs/after-render")
    for name, sha in config["engine_snapshot"].items():
        verify_source(root / "scripts/episode_post" / name, sha)
    config.update({"rendered_subtitle_cues": [asdict(c) for c in captions],
                   "displayed_subtitle_cues": [asdict(c) for c in displayed],
                   "ending_layout": layout, "measured_unit_staging": staging,
                   "sfx_cues": audio_qc["sfx_cues"], "output_frames": layout["total_frames"]})
    save(out / "edit_manifest.json", config)
    report = {"status": "TECHNICAL_PASS_EDITORIAL_REVIEW_REQUIRED", "episode": shared["episode"],
              "agent_id": plan["agent_id"], "outputs": outputs, "ending_layout": layout,
              "expected_frames": layout["total_frames"], "subtitle_cues": len(captions),
              "original_hashes_unchanged": True, "full_watch_review": "NOT_DONE", "audio_qc": audio_qc}
    save(out / "qc_report.json", report)
    (out / "MUSIC_CREDITS.txt").write_text(
        "'Undertow' by Scott Buckley - CC-BY 4.0. www.scottbuckley.com.au\n"
        "https://www.scottbuckley.com.au/library/undertow/\nhttps://creativecommons.org/licenses/by/4.0/\n"
        "Changes: excerpts, fades, level changes, dialogue ducking and mixed locally synthesized SFX.\n"
        "Include full attribution in the publication description.\n")
    print(json.dumps({"out": str(out), "frames": layout["total_frames"], "seconds": layout["total_frames"] / 24,
                      "sha256": outputs[1]["sha256"]}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shared", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    render(args.root.resolve(), args.shared.resolve(), args.plan.resolve(), args.out.resolve())


if __name__ == "__main__":
    main()
