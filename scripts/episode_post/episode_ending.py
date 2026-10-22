"""Frame-accurate bloom/hold ending and independently materialized suspense stems."""
from __future__ import annotations

from pathlib import Path

from ep_pilot_media import run_logged
from ep_pilot_timeline import Clip


def ending_layout(story_frames: int, preset: dict, tail_pad_frames: int = 0) -> dict:
    if preset["id"] != "bloom-hold-suspense" or preset["version"] != 1:
        raise ValueError("unsupported ending preset")
    # tail_pad_frames freezes the last story frame (silently) before the
    # bloom sequence, for episodes whose final line ends too close to the
    # last unit's tail for the effect to start after dialogue.
    if not isinstance(tail_pad_frames, int) or not 0 <= tail_pad_frames <= 96:
        raise ValueError("tail_pad_frames must be an int in [0, 96]")
    timing = preset["timeline_seconds"]
    hold = round(timing["additional_hold"] * 24)
    card = round(timing["card_duration"] * 24)
    if story_frames < 90 or hold != 24 or card != 30:
        raise ValueError("unsupported ending layout")
    effective = story_frames + tail_pad_frames
    offset = effective / 24 - timing["motion_end"]
    return {"story_frames": story_frames, "tail_pad_frames": tail_pad_frames,
            "hold_frames": hold, "card_frames": card,
            "total_frames": effective + hold + card,
            "bloom_start_s": offset + timing["bloom_start"],
            "bloom_full_s": offset + timing["bloom_full"],
            "hold_start_s": effective / 24,
            "card_start_s": (effective + hold) / 24,
            "preset_offset_s": offset}


def bloom_filter(frames: int, preset: dict) -> str:
    if frames < 90:
        raise ValueError("last clip too short for the approved bloom sequence")
    video, timing = preset["video"], preset["timeline_seconds"]
    offset = frames / 24 - timing["motion_end"]
    start = offset + timing["bloom_start"]
    ramp = timing["bloom_full"] - timing["bloom_start"]
    weight = f"min(max((T-{start:.9f})/{ramp:.9f},0),1)"
    high = ":".join(f"{c}='clip((val-{video['highlight_threshold_rgb_8bit']})*"
                    f"{video['highlight_gain']},0,255)'" for c in "rgb")
    return ("format=gbrp,split=3[clear][body][light];"
            f"[light]lutrgb={high},gblur=sigma={video['highlight_blur_sigma']}[glow];"
            f"[body][glow]blend=all_mode=screen,gblur=sigma={video['soft_focus_sigma']},"
            f"eq=brightness={video['brightness']}[soft];"
            f"[clear][soft]blend=all_expr='A*(1-({weight}))+B*({weight})',"
            f"format=yuv420p,tpad=stop={round(timing['additional_hold'] * 24)}:stop_mode=clone[v]")


def render_bloom_segment(source: Path, dest: Path, clip: Clip, gain: float,
                         preset: dict, log: Path, tail_pad_frames: int = 0) -> None:
    if not isinstance(tail_pad_frames, int) or not 0 <= tail_pad_frames <= 96:
        raise ValueError("tail_pad_frames must be an int in [0, 96]")
    frames = clip.out_frame - clip.in_frame + tail_pad_frames
    duration, source_end = (clip.out_frame - clip.in_frame) / 24, clip.out_frame / 24
    total = frames / 24 + preset["timeline_seconds"]["additional_hold"]
    pad = f"tpad=stop={tail_pad_frames}:stop_mode=clone," if tail_pad_frames else ""
    graph = (f"[0:v]trim=start_frame={clip.in_frame}:end_frame={clip.out_frame},"
             "setpts=PTS-STARTPTS," + pad + bloom_filter(frames, preset) + ";"
             f"[0:a]atrim=start={clip.in_frame / 24}:end={source_end},"
             f"asetpts=PTS-STARTPTS,aresample=48000,volume={gain}dB,"
             f"afade=t=out:st={duration - 0.03}:d=0.03,apad,atrim=duration={total}[a]")
    run_logged(["ffmpeg", "-nostdin", "-v", "error", "-n", "-i", str(source),
                "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
                "-c:v", "libx264", "-preset", "fast", "-crf", "16",
                "-pix_fmt", "yuv420p", "-c:a", "pcm_s24le", str(dest)], log)


def render_sfx(preset: dict, layout: dict, out: Path, gain_db: float) -> tuple[list[Path], list[dict]]:
    paths, cues = [], []
    total = layout["total_frames"] / 24
    for item in preset["sfx"]:
        start = layout["preset_offset_s"] + item["start"]
        end = layout["preset_offset_s"] + item["end"]
        if not 0 <= start < end <= total:
            raise ValueError("SFX falls outside the ending timeline")
        path = out / "work" / f"sfx-{item['id']}.wav"
        filters = (item["filters"] + f",volume={gain_db}dB,aformat=channel_layouts=stereo,"
                   f"adelay={round(start * 48000)}S:all=1,asetpts=N/SR/TB,apad,"
                   f"atrim=duration={total},asetpts=N/SR/TB")
        run_logged(["ffmpeg", "-nostdin", "-v", "error", "-n", "-f", "lavfi",
                    "-i", item["generator"], "-af", filters, "-ar", "48000",
                    "-ac", "2", "-c:a", "pcm_f32le", str(path)],
                   out / "logs" / f"sfx-{item['id']}.log")
        paths.append(path)
        cues.append({"id": item["id"], "start": start, "end": end, "gain_db": gain_db})
    return paths, cues
