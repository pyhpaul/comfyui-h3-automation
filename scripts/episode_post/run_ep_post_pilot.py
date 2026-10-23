#!/usr/bin/env python3
"""Render and technically validate the reviewed EP01 pilot manifest."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re

from ep_pilot_media import (
    concatenate, export_video, loudness, mix_music, normalize_audio,
    probe, render_endcard, render_segment, run_logged,
)
from ep_pilot_audio_qc import check_music_timing
from ep_pilot_creative import validate_protected_ranges
from ep_pilot_mix import mix_pcm_tracks
from ep_pilot_timeline import (
    Clip, Subtitle, Word, align_dialogue, remap_subtitles, render_srt,
    presentation_cues, validate_clips, verify_source, wrap_caption,
)


def save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def source_words(unit: str, source: dict) -> list[Word]:
    data = json.loads(Path(source["analysis"]).read_text())
    if data["sha256"] != source["sha256"]:
        raise ValueError(f"ASR source identity mismatch: {unit}")
    return [Word(unit, word["start"], word["end"], word["word"])
            for segment in data["segments"] for word in segment["words"]]


def collect_captions(config: dict, clips: list[Clip]) -> tuple[list[Subtitle], list[Subtitle]]:
    captions: list[Subtitle] = []
    retained_words: list[Subtitle] = []
    for unit, source in config["sources"].items():
        words = source_words(unit, source)
        prompt = Path(source["prompt"]).read_text()
        body = prompt.split("【画面内容】", 1)[1].split("【H3 latent", 1)[0]
        lines = [line.strip() for line in re.findall(r"（\s*([A-Za-z][^）]+)）", body)]
        skip_first = {item["phrase"] for item in config.get("alignment_skips", [])
                      if item["unit"] == unit}
        captions.extend(align_dialogue(lines, words, config["subtitle_aliases"], skip_first))
        for word in words:
            if word.end <= word.start:
                continue
            if any(c.unit == unit and c.in_frame / 24 <= word.start < word.end <= c.out_frame / 24
                   for c in clips):
                retained_words.append(Subtitle(unit, word.start, word.end, word.text))
    return remap_subtitles(captions, clips), remap_subtitles(retained_words, clips)


def ass_time(seconds: float) -> str:
    total = round(seconds * 100)
    hours, remainder = divmod(total, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, centis = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


_ZH_IN_PAREN = re.compile(
    r"^(?P<en>.+?)（(?P<zh>[\u4e00-\u9fffA-Za-z0-9，。！？、；：…「」『』\s'\-]+)）$"
)


def extract_zh_from_bilingual(line: str) -> str | None:
    """Pull Chinese from `English.（中文）` when packs embed both in one cue."""
    match = _ZH_IN_PAREN.match(line.strip())
    return match.group("zh").strip() if match else None


def resolve_zh_captions(readable: list[Subtitle], config: dict) -> list[str]:
    """Chinese phrase texts aligned 1:1 with displayed English cues.

    Prefer explicit `zh_captions` (creative plan / manifest). Fall back to
    bilingual English cues that embed `（中文）`. Missing coverage fails loud.
    """
    explicit = config.get("zh_captions")
    if explicit is not None:
        if len(explicit) != len(readable):
            raise ValueError(
                f"zh_captions length {len(explicit)} != English cues {len(readable)}")
        texts = [str(t).strip() for t in explicit]
        if any(not t for t in texts):
            raise ValueError("zh_captions contains empty lines")
        return texts
    texts = []
    for cue in readable:
        zh = extract_zh_from_bilingual(cue.text)
        if not zh:
            raise ValueError(
                "Chinese word track required: set zh_captions on the plan "
                f"(missing for English cue {cue.text!r})")
        texts.append(zh)
    return texts


def _write_ass(path: Path, cues: list[Subtitle], style: dict, *, font: str) -> None:
    header = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 768\nPlayResY: 1376\nWrapStyle: 2\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
        "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Dialogue,{font},{style.get('font_size', 34)},&H00F1F3F6,&H00FFFFFF,&H00141210,&H80000000,"
        f"0,0,0,0,100,100,0,0,1,{style.get('outline', 1.8)},0.6,2,64,64,170,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    events = []
    for cue in cues:
        text = wrap_caption(cue.text).replace("\n", r"\N")
        events.append(
            f"Dialogue: 0,{ass_time(cue.start)},{ass_time(cue.end)},Dialogue,,0,0,0,,{text}\n")
    path.write_text(header + "".join(events), encoding="utf-8")


def write_subtitles(out: Path, cues: list[Subtitle], words: list[Subtitle],
                    style: dict | None = None, episode: str = "EP01",
                    config: dict | None = None) -> list[Subtitle]:
    style = style or {}
    readable = presentation_cues(cues, style)
    (out / f"{episode}.en.srt").write_text(render_srt(readable), encoding="utf-8")
    (out / f"{episode}.words.srt").write_text(render_srt(words), encoding="utf-8")
    _write_ass(out / f"{episode}.en.ass", readable, style, font="DejaVu Sans")
    # Chinese phrase track shares English cue timing (not ASR word splits).
    # Off by default so legacy pilots keep working; lihun comparison turns it on.
    if config is not None and config.get("require_zh_captions", False):
        zh_texts = resolve_zh_captions(readable, config)
        zh_cues = [Subtitle(c.unit, c.start, c.end, text)
                   for c, text in zip(readable, zh_texts)]
        (out / f"{episode}.zh.srt").write_text(render_srt(zh_cues), encoding="utf-8")
        _write_ass(out / f"{episode}.zh.ass", zh_cues, style,
                   font=str(style.get("zh_font", "Noto Sans CJK SC")))
    return readable


def validate_sources(config: dict, logs: Path) -> dict[str, dict]:
    if config["fps"] != 24 or (config["width"], config["height"]) != (768, 1376):
        raise ValueError("pilot supports only verified 768x1376 24fps source contract")
    probes = {}
    for unit, source in config["sources"].items():
        verify_source(Path(source["path"]), source["sha256"])
        verify_source(Path(source["prompt"]), source["prompt_sha256"])
        data = probe(Path(source["path"]), logs / f"probe-{unit}.log")
        video = next(stream for stream in data["streams"] if stream["codec_type"] == "video")
        if (video["width"], video["height"], video["avg_frame_rate"]) != (768, 1376, "24/1"):
            raise ValueError(f"unsupported source geometry: {unit}")
        probes[unit] = data
    verify_source(Path(config["music"]["path"]), config["music"]["sha256"])
    for cue in config["music"]["cues"]:
        if "path" in cue:
            verify_source(Path(cue["path"]), cue["sha256"])
    return probes


def render_picture(config: dict, clips: list[Clip], out: Path, logs: Path) -> tuple[Path, list[dict]]:
    parts, stages = [], []
    for i, clip in enumerate(clips):
        source = Path(config["sources"][clip.unit]["path"])
        duration = (clip.out_frame - clip.in_frame) / 24
        levels = loudness(source, logs / f"levels-{i}.log", clip.in_frame / 24, duration)
        gain = round(max(-6, min(6, -18 - float(levels["input_i"]))), 3)
        part = out / f"work/part-{i}.mkv"
        render_segment(source, part, clip.in_frame, clip.out_frame, gain,
                       i == len(clips) - 1, logs / f"render-part-{i}.log",
                       config.get("ending_push"))
        parts.append(part)
        stages.append({"unit": clip.unit, "input_lufs": levels["input_i"], "gain_db": gain})
    tail = out / "work/endcard.mkv"
    render_endcard(tail, config["endcard_frames"], logs / "endcard.log",
                   config.get("endcard", {}).get("show_music_credit", True))
    picture = out / "work/picture.mkv"
    concatenate(parts + [tail], picture, logs / "concat.log")
    return picture, stages


def check_output(path: Path, expected_frames: int, logs: Path) -> dict:
    data = probe(path, logs / f"probe-{path.stem}.log")
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    audio = next(s for s in data["streams"] if s["codec_type"] == "audio")
    if int(video["nb_frames"]) != expected_frames:
        raise ValueError(f"frame count mismatch: {path}")
    if abs(float(video["duration"]) - float(audio["duration"])) > 1 / 24:
        raise ValueError(f"AV duration mismatch: {path}")
    run_logged(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-f", "null", "-"],
               logs / f"decode-{path.stem}.log")
    levels = loudness(path, logs / f"loudness-{path.stem}.log")
    if abs(float(levels["input_i"]) + 16) > 0.6 or float(levels["input_tp"]) > -1:
        raise ValueError(f"encoded output exceeds audio target: {levels}")
    return {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size, "probe": data, "loudness": levels,
            "decode_passed": True, "frames_passed": True, "av_duration_passed": True}


def render(config: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=False)
    (out / "work").mkdir()
    logs = out / "logs"
    probes = validate_sources(config, logs)
    clips = [Clip(c["unit"], c["in_frame"], c["out_frame"]) for c in config["clips"]]
    frames = {unit: int(next(s for s in p["streams"] if s["codec_type"] == "video")["nb_frames"])
              for unit, p in probes.items()}
    validate_clips(clips, frames)
    validate_protected_ranges(config.get("protected_ranges", []), clips)
    cues, words = collect_captions(config, clips)
    # Legacy pilots may omit zh; lihun delivery sets require_zh_captions (default).
    displayed = write_subtitles(out, cues, words, config.get("subtitle_style"),
                                config.get("episode", "EP01"), config)
    total_frames = sum(c.out_frame - c.in_frame for c in clips) + config["endcard_frames"]
    save(out / "edit_manifest.json", config)
    if "creative_plan" in config:
        save(out / "creative_plan.json", config["creative_plan"])
    picture, stages = render_picture(config, clips, out, logs)
    music = config["music"]
    music_levels = loudness(Path(music["path"]), logs / "music-levels.log")
    music_gain = music["target_lufs_before_duck"] - float(music_levels["input_i"])
    mixed = out / "work/mix.wav"
    mix_music(picture, Path(music["path"]), music["cues"], mixed,
              music_gain, total_frames / 24, logs / "mix.log",
              [(cue.start, cue.end) for cue in cues])
    music["ducking"] = json.loads((logs / "mix.automation.json").read_text())
    music_qc = check_music_timing(picture, mixed, music["cues"], total_frames / 24)
    save(out / "music_timing_qc.json", music_qc)
    measurement = loudness(mixed, logs / "mix-first-pass.log")
    normalized = out / "work/normalized.wav"
    normalize_audio(mixed, normalized, measurement, logs / "mix-second-pass.log")
    # Master: dialogue only (no BGM). Pilot has no ending SFX stem here.
    dialogue_only = out / "work/dialogue-only.wav"
    mix_pcm_tracks(picture, [], dialogue_only, total_frames / 24, [],
                   logs / "dialogue-only.log")
    master_meas = loudness(dialogue_only, logs / "master-first-pass.log")
    master_audio = out / "work/master-normalized.wav"
    normalize_audio(dialogue_only, master_audio, master_meas,
                    logs / "master-second-pass.log")
    episode = config.get("episode", "EP01")
    outputs = []
    for name, audio, subtitles, credit in (
        (f"{episode}-master.mp4", master_audio, None, False),
        (f"{episode}-review-en.mp4", normalized, out / f"{episode}.en.ass", True),
    ):
        path = out / name
        export_video(picture, audio, path, logs / f"export-{name}.log", subtitles,
                     music_credit=credit)
        outputs.append(check_output(path, total_frames, logs))
    validate_sources(config, logs / "after-render")
    config["measured_unit_staging"] = stages
    config["rendered_subtitle_cues"] = [asdict(c) for c in cues]
    config["displayed_subtitle_cues"] = [asdict(c) for c in displayed]
    config["output_frames"] = total_frames
    config["music"]["measured_gain_db"] = music_gain
    if "creative_plan" in config:
        config["creative_plan"]["execution_status"] = "RENDERED_TECHNICAL_CHECKS_PASSED"
        config["creative_plan"]["perceptual_review"] = "NOT_DONE"
        save(out / "creative_plan.json", config["creative_plan"])
    save(out / "edit_manifest.json", config)
    credits = (music["credit"] + "\n" + music["source_url"] + "\n" + music["license_url"] +
               "\nChanges: " + music["adaptation"] +
               "\nFor YouTube publication, include this attribution in the video description.\n")
    (out / "MUSIC_CREDITS.txt").write_text(credits)
    report = {"status": "TECHNICAL_PASS_EDITORIAL_REVIEW_REQUIRED", "episode": "EP01",
              "source_version": config["source_version"], "original_hashes_unchanged": True,
              "expected_frames": total_frames, "subtitle_cues": len(cues),
              "scripted_phrases_retained": len(cues), "word_cues": len(words),
              "full_watch_review": "NOT_DONE", "outputs": outputs,
              "music_timing": music_qc,
              "editorial_risks": config["review_notes"]}
    save(out / "qc_report.json", report)
    print(json.dumps({"out": str(out), "frames": total_frames, "seconds": total_frames / 24,
                      "subtitle_cues": len(cues), "status": report["status"]}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    render(json.loads(args.manifest.read_text()), args.out.resolve())


if __name__ == "__main__":
    main()
