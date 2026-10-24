"""FFmpeg I/O for the bounded EP pilot; every command retains a log."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess

from ep_pilot_mix import mix_pcm_tracks
from ep_pilot_creative import cue_fades, ending_video_filter
from ep_pilot_audio_qc import check_residual_windows, decode_stereo


def video_encode_args(*, role: str = "intermediate") -> list[str]:
    """H.264 encode args for episode-post ffmpeg graph outputs.

    Roles:
      - intermediate: unit parts / bloom / endcard / concat picture
      - burnin: review ASS burn-in (was the slow libx264 -preset slow path)

    Default NVENC (`H3_EP_VIDEO_ENCODER` unset or `nvenc`). Set
    `H3_EP_VIDEO_ENCODER=libx264` for CPU parity / no NVENC.
    """
    choice = os.environ.get("H3_EP_VIDEO_ENCODER", "nvenc").strip().lower()
    if role not in {"intermediate", "burnin", "concat"}:
        raise ValueError(f"unknown encode role: {role}")
    if choice in {"libx264", "x264", "cpu"}:
        if role == "burnin":
            return ["-c:v", "libx264", "-preset", "slow", "-crf", "18"]
        crf = "17" if role == "concat" else "16"
        return ["-c:v", "libx264", "-preset", "fast", "-crf", crf, "-pix_fmt", "yuv420p"]
    # NVENC: cq 19 ≈ burn-in CRF18; cq 17 ≈ intermediate CRF16/17.
    cq = "19" if role == "burnin" else "17"
    return [
        "-c:v", "h264_nvenc",
        "-preset", "p4",
        "-cq", cq,
        "-b:v", "0",
        "-pix_fmt", "yuv420p",
    ]


def burnin_video_encode_args() -> list[str]:
    """Backward-compatible alias for review burn-in encode args."""
    return video_encode_args(role="burnin")


def run_logged(args: list[str], log: Path) -> str:
    result = subprocess.run(args, capture_output=True, text=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps(args) + "\n\n" + result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}); see {log}")
    return result.stdout + result.stderr


def probe(path: Path, log: Path) -> dict:
    return json.loads(run_logged([
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path),
    ], log))


def loudness(path: Path, log: Path, start: float = 0, duration: float | None = None,
             true_peak_target: float = -1.5) -> dict:
    args = ["ffmpeg", "-nostdin", "-hide_banner", "-ss", str(start), "-i", str(path)]
    if duration is not None:
        args += ["-t", str(duration)]
    args += ["-vn", "-af", f"loudnorm=I=-16:TP={true_peak_target}:LRA=9:print_format=json",
             "-f", "null", "-"]
    output = run_logged(args, log)
    matches = re.findall(r'\{\s*"input_i".*?\}', output, re.S)
    if not matches:
        raise RuntimeError(f"missing loudness measurement: {log}")
    return json.loads(matches[-1])


def render_segment(source: Path, dest: Path, start_frame: int, end_frame: int,
                   gain_db: float, ending: bool, log: Path,
                   ending_push: dict | None = None) -> None:
    start, duration = start_frame / 24, (end_frame - start_frame) / 24
    video = f"trim=start_frame={start_frame}:end_frame={end_frame},setpts=PTS-STARTPTS"
    if ending:
        push = ending_video_filter(ending_push, end_frame - start_frame)
        if push:
            video += "," + push
        video += f",fade=t=out:st={duration - 0.25}:d=0.25"
    audio = (f"atrim=start={start}:end={end_frame / 24},asetpts=PTS-STARTPTS,"
             f"aresample=48000,apad,atrim=duration={duration},volume={gain_db}dB,"
             f"afade=t=out:st={duration - 0.005}:d=0.005")
    run_logged([
        "ffmpeg", "-nostdin", "-hide_banner", "-n", "-i", str(source),
        "-filter_complex", f"[0:v]{video}[v];[0:a]{audio}[a]",
        "-map", "[v]", "-map", "[a]", *video_encode_args(role="intermediate"),
        "-c:a", "pcm_s24le", str(dest),
    ], log)


def render_endcard(dest: Path, frames: int, log: Path,
                   show_music_credit: bool = True, episode: str = "EP01") -> None:
    serif = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
    sans = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    styles = [
        f"drawtext=fontfile={sans}:text='EPISODE {episode[2:]}':fontsize=22:fontcolor=0xb8a481:x=(w-tw)/2:y=572",
        "drawbox=x=(iw-72)/2:y=622:w=72:h=2:color=0xb8a481:t=fill",
        f"drawtext=fontfile={serif}:text='TO BE CONTINUED':fontsize=42:fontcolor=0xf3efe7:x=(w-tw)/2:y=658",
    ]
    if show_music_credit:
        styles.extend([
            f"drawtext=fontfile={sans}:text='Music - Undertow by Scott Buckley':fontsize=18:fontcolor=0xaaa9a5:x=(w-tw)/2:y=1160",
            f"drawtext=fontfile={sans}:text='CC-BY 4.0 / scottbuckley.com.au':fontsize=18:fontcolor=0xaaa9a5:x=(w-tw)/2:y=1188",
        ])
    styles.append("fade=t=in:st=0:d=0.167")
    run_logged([
        "ffmpeg", "-nostdin", "-hide_banner", "-n", "-f", "lavfi", "-i",
        f"color=c=0x101418:s=768x1376:r=24:d={frames / 24}",
        "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={frames / 24}",
        "-vf", ",".join(styles), *video_encode_args(role="intermediate"),
        "-c:a", "pcm_s24le", "-shortest", str(dest),
    ], log)


def concatenate(paths: list[Path], dest: Path, log: Path,
                expected_frames: int | None = None) -> None:
    args = ["ffmpeg", "-nostdin", "-hide_banner", "-n"]
    for path in paths:
        args += ["-i", str(path)]
    inputs = "".join(f"[{i}:v][{i}:a]" for i in range(len(paths)))
    graph = inputs + f"concat=n={len(paths)}:v=1:a=1[v][a]"
    if expected_frames is not None:
        samples = expected_frames * 2000  # 48 kHz / 24 fps; MKV timestamps round to milliseconds.
        if sum(len(decode_stereo(path)) for path in paths) != samples:
            raise ValueError("source PCM lengths differ from frame-locked timeline")
        graph = inputs + f"concat=n={len(paths)}:v=1:a=1[v][joined]"
        graph += f";[joined]apad,atrim=end_sample={samples},asetpts=N/SR/TB[a]"
    args += ["-filter_complex", graph,
             "-map", "[v]", "-map", "[a]", *video_encode_args(role="concat"),
             "-c:a", "pcm_s24le", str(dest)]
    run_logged(args, log)


def render_music_cue(music: Path, cue: dict, dest: Path, gain: float,
                     total: float, log: Path) -> None:
    duration = cue["end"] - cue["start"]
    fade_in, fade_out = cue_fades(cue, total)
    fades = (f"afade=t=in:d={fade_in}," if fade_in else "")
    if fade_out:
        # Fixed-point: float dust like 1e-15 (fade_out == duration) would
        # otherwise render in scientific notation, which ffmpeg rejects.
        fades += f"afade=t=out:st={duration - fade_out:.6f}:d={fade_out},"
    settings = (
        f"aresample=48000,atrim=start={cue['source_in']}:duration={duration},asetpts=N/SR/TB,"
        f"volume={gain}dB,{fades}"
        f"adelay={round(cue['start'] * 1000)}:all=1,asetpts=N/SR/TB,"
        f"apad,atrim=duration={total},asetpts=N/SR/TB")
    run_logged([
        "ffmpeg", "-nostdin", "-hide_banner", "-n", "-i", str(music),
        "-af", settings, "-ar", "48000", "-ac", "2", "-c:a", "pcm_f32le", str(dest),
    ], log)


def mix_music(picture: Path, music: Path, cues: list[dict], dest: Path,
              music_gain_db: float, total: float, log: Path,
              speech_intervals: list[tuple[float, float]] | None = None) -> None:
    # Materialized cues avoid timing and finite-sidechain EOF losses in the shared filter graph.
    tracks = []
    for i, cue in enumerate(cues):
        path = dest.with_name(f"{dest.stem}-cue-{i}.wav")
        cue_source = Path(cue.get("path", music))
        render_music_cue(cue_source, cue, path,
                         music_gain_db + cue.get("gain_offset_db", 0), total,
                         log.with_name(f"{log.stem}-cue-{i}.log"))
        check_residual_windows(decode_stereo(path), 48000, [cue], total)
        tracks.append(path)
    mix_pcm_tracks(picture, tracks, dest, total, speech_intervals or [], log)


def normalize_audio(source: Path, dest: Path, measurement: dict, log: Path,
                     true_peak_target: float = -1.5) -> None:
    settings = f"loudnorm=I=-16:TP={true_peak_target}:LRA=9:linear=true:print_format=json"
    for field, value in (("measured_I", "input_i"), ("measured_TP", "input_tp"),
                         ("measured_LRA", "input_lra"), ("measured_thresh", "input_thresh"),
                         ("offset", "target_offset")):
        settings += f":{field}={measurement[value]}"
    run_logged([
        "ffmpeg", "-nostdin", "-hide_banner", "-n", "-i", str(source),
        "-af", settings, "-ar", "48000", "-c:a", "pcm_s24le", str(dest),
    ], log)


def export_video(picture: Path, audio: Path, dest: Path, log: Path,
                  subtitles: Path | None = None, *, music_credit: bool = True) -> None:
    args = ["ffmpeg", "-nostdin", "-hide_banner", "-n", "-i", str(picture), "-i", str(audio),
            "-map", "0:v:0", "-map", "1:a:0"]
    if subtitles:
        # Burn-in forces re-encode; master path stays stream-copy.
        args += ["-vf", f"ass=filename='{subtitles}'", *video_encode_args(role="burnin")]
    else:
        args += ["-c:v", "copy"]
    comment = (
        "Music: Undertow by Scott Buckley; CC-BY 4.0; www.scottbuckley.com.au; excerpted, faded and mixed."
        if music_credit else
        "Dialogue/SFX master; no BGM bed."
    )
    args += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             "-metadata", f"comment={comment}",
             "-movflags", "+faststart", "-shortest", str(dest)]
    run_logged(args, log)
