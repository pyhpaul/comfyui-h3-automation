"""Bind ComfyUI history outputs to source-side bytes for Gate 0 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
import subprocess
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any
from dataclasses import dataclass

from h3_a100_media import decoded_stream_sha256, media_timeline, media_timeline_sha256


EXPECTED_SHAPES = {"audio": [1, 32, 2, 547], "video": [1, 24, 97, 86, 48]}


@dataclass(frozen=True)
class AudioContract:
    sample_rate: int
    channels: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prefix_inventory(root: Path, prefix: str) -> list[str]:
    """Call before submission and save the empty result beside the ready file."""
    if not prefix or Path(prefix).is_absolute() or ".." in Path(prefix).parts:
        raise ValueError("unsafe output prefix")
    target = root / prefix
    return sorted(str(path.relative_to(root)) for path in target.parent.glob(target.name + "_*"))


def prefix_baseline(root: Path, prefix: str, run_id: str | None = None) -> dict[str, Any]:
    return {"root": str(root.resolve(strict=True)), "prefix": prefix,
            "run_id": run_id,
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "files": prefix_inventory(root, prefix)}


def _check_baseline(baseline: dict[str, Any], root: Path, prefix: str,
                    history_start_ms: int, run_id: str | None = None) -> None:
    if baseline.get("root") != str(root.resolve(strict=True)) \
            or baseline.get("prefix") != prefix or baseline.get("files") != [] \
            or (run_id is not None and baseline.get("run_id") != run_id):
        raise ValueError("output prefix baseline is occupied or mismatched")
    captured = datetime.fromisoformat(baseline["captured_at_utc"])
    if captured.tzinfo is None or int(captured.timestamp() * 1000) > history_start_ms:
        raise ValueError("output prefix baseline was not captured before submission")


def _bound_path(raw: str, root: Path, prefix: str, suffix: str) -> Path:
    if not prefix or Path(prefix).is_absolute() or ".." in Path(prefix).parts:
        raise ValueError("unsafe output prefix")
    if not isinstance(raw, str) or not Path(raw).is_absolute():
        raise ValueError("history output path is not absolute")
    root_resolved = root.resolve(strict=True)
    path = Path(raw)
    resolved = path.resolve(strict=True)
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("history output is symlink redirected")
    if not resolved.is_relative_to(root_resolved) or path.is_symlink():
        raise ValueError("history output escapes root or is a symlink")
    expected = root_resolved / prefix
    if resolved.parent != expected.parent \
            or not resolved.name.startswith(expected.name + "_") \
            or resolved.suffix != suffix:
        raise ValueError("history output has foreign prefix or format")
    if resolved.stat().st_size <= 0:
        raise ValueError("history output is empty")
    return resolved


def history_output_paths(history: dict[str, Any], prompt_id: str, root: Path,
                         video_prefix: str, latent_prefix: str,
                         video_baseline: dict[str, Any], latent_baseline: dict[str, Any],
                         run_id: str | None = None) -> tuple[Path, Path]:
    if set(history) != {prompt_id}:
        raise ValueError("history is not isolated to target prompt")
    record = history[prompt_id]
    if record.get("status", {}).get("status_str") != "success" \
            or record.get("status", {}).get("completed") is not True:
        raise ValueError("target prompt did not succeed")
    messages = record["status"]["messages"]
    starts = [data.get("timestamp") for kind, data in messages if kind == "execution_start"
              and data.get("prompt_id") == prompt_id]
    if len(starts) != 1 or not isinstance(starts[0], int):
        raise ValueError("history start timestamp is missing")
    _check_baseline(video_baseline, root, video_prefix, starts[0], run_id)
    _check_baseline(latent_baseline, root, latent_prefix, starts[0], run_id)
    graph = record["prompt"][2]
    if graph["264"]["inputs"]["filename_prefix"] != video_prefix \
            or graph["400"]["inputs"]["filename_prefix"] != latent_prefix \
            or graph["405"]["inputs"]["source"] != ["400", 0]:
        raise ValueError("history graph output prefixes differ")
    outputs = record["outputs"]
    videos = outputs["264"]["gifs"]
    latents = outputs["405"]["text"]
    if len(videos) != 1 or len(latents) != 1 or videos[0].get("type") != "output" \
            or videos[0].get("format") != "video/h264-mp4":
        raise ValueError("history output node shape differs")
    video = _bound_path(videos[0]["fullpath"], root, video_prefix, ".mp4")
    latent = _bound_path(latents[0], root, latent_prefix, ".safetensors")
    if video.name != videos[0].get("filename"):
        raise ValueError("video filename differs from history")
    if video.stat().st_mtime_ns < (starts[0] - 2000) * 1_000_000 \
            or latent.stat().st_mtime_ns < (starts[0] - 2000) * 1_000_000:
        raise ValueError("history output appears older than the prompt")
    return video, latent


def inspect_latent(path: Path, expected_shapes: dict[str, list[int]] = EXPECTED_SHAPES) -> dict[str, Any]:
    """Validate the small safetensors header and stream all F32 values for finiteness."""
    size = path.stat().st_size
    with path.open("rb") as source:
        header_size_raw = source.read(8)
        if len(header_size_raw) != 8:
            raise ValueError("short safetensors header")
        header_size = struct.unpack("<Q", header_size_raw)[0]
        if not 0 < header_size <= 1_000_000 or 8 + header_size >= size:
            raise ValueError("invalid safetensors header size")
        header = json.loads(source.read(header_size))
        keys = {key for key in header if key != "__metadata__"}
        if keys != set(expected_shapes):
            raise ValueError("latent tensor names differ")
        ranges: list[tuple[int, int]] = []
        for key, shape in expected_shapes.items():
            tensor = header[key]
            begin, end = tensor["data_offsets"]
            if tensor["dtype"] != "F32" or tensor["shape"] != shape \
                    or not isinstance(begin, int) or not isinstance(end, int) \
                    or end - begin != math.prod(shape) * 4:
                raise ValueError(f"latent tensor layout differs: {key}")
            ranges.append((begin, end))
        ranges.sort()
        if ranges[0][0] != 0 or ranges[-1][1] != size - 8 - header_size \
                or any(left[1] != right[0] for left, right in zip(ranges, ranges[1:])):
            raise ValueError("latent tensor data has gaps or overlap")
        for begin, end in ranges:
            source.seek(8 + header_size + begin)
            remaining = end - begin
            while remaining:
                chunk = source.read(min(remaining, 4 * 65536))
                if not chunk or len(chunk) % 4:
                    raise ValueError("latent tensor data is truncated")
                if any(not math.isfinite(item[0]) for item in struct.iter_unpack("<f", chunk)):
                    raise ValueError("latent tensor contains nonfinite values")
                remaining -= len(chunk)
    return {"bytes": size, "sha256": sha256_file(path),
            "shapes": expected_shapes, "dtype": "F32", "finite": True}


def _probe_streams(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,codec_name,width,height,r_frame_rate,start_time,duration,nb_frames,sample_rate,channels",
         "-of", "json", str(path)], capture_output=True, text=True, check=True, timeout=120)
    streams = json.loads(result.stdout).get("streams", [])
    video_streams = [item for item in streams if item.get("codec_type") == "video"]
    audio_streams = [item for item in streams if item.get("codec_type") == "audio"]
    if len(video_streams) != 1 or len(audio_streams) != 1:
        raise ValueError("expected exactly one video and one audio stream")
    return video_streams[0], audio_streams[0]


def validate_av_alignment(video: dict[str, Any], audio: dict[str, Any]) -> None:
    video_start = float(video["start_time"])
    audio_start = float(audio["start_time"])
    video_duration = float(video["duration"])
    audio_duration = float(audio["duration"])
    if not all(math.isfinite(value) for value in
               (video_start, audio_start, video_duration, audio_duration)) \
            or video_duration <= 0 or audio_duration <= 0 \
            or abs(video_start - audio_start) > 0.05 \
            or abs(video_duration - audio_duration) > 0.05:
        raise ValueError("audio and video are time-shifted")


def validate_audio_timestamps(timeline: dict[str, Any]) -> None:
    stream = timeline["stream"]
    sample_rate = int(stream["sample_rate"])
    time_base = Fraction(stream["time_base"])
    frames = timeline["frames"]
    timestamps = [int(frame["best_effort_timestamp"]) for frame in frames]
    sample_counts = [int(frame["nb_samples"]) for frame in frames]
    if sample_rate <= 0 or time_base <= 0 or not timestamps \
            or any(count <= 0 for count in sample_counts) \
            or any(right <= left for left, right in zip(timestamps, timestamps[1:])):
        raise ValueError("audio timeline has missing or regressed timestamps")
    for index, (left, right) in enumerate(zip(timestamps, timestamps[1:])):
        expected_ticks = Fraction(sample_counts[index], sample_rate) / time_base
        if abs(Fraction(right - left) - expected_ticks) > 1:
            raise ValueError("audio timeline has an internal gap or overlap")


def _audio_max_db(path: Path) -> float:
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-i", str(path),
         "-vn", "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, check=True, timeout=120)
    match = re.search(r"max_volume:\s*([\d.-]+) dB", result.stderr)
    if not match or float(match.group(1)) < -60:
        raise ValueError("audio is silent or unexpectedly quiet")
    return float(match.group(1))


def inspect_video(path: Path, audio_contract: AudioContract | None = None) -> dict[str, Any]:
    video, audio = _probe_streams(path)
    if video.get("codec_name") != "h264" or audio.get("codec_name") != "aac" \
            or (video.get("width"), video.get("height")) != (768, 1376) \
            or video.get("r_frame_rate") != "24/1":
        raise ValueError("video codec, dimensions or frame rate differ")
    video_timeline = media_timeline(path, "video")
    audio_timeline = media_timeline(path, "audio")
    if video_timeline["frame_count"] != 306 or audio_timeline["frame_count"] <= 0 \
            or not 12.70 <= float(video.get("duration", 0)) <= 12.80 \
            or not 12.50 <= float(audio.get("duration", 0)) <= 13.00:
        raise ValueError("video frames, audio or duration differ")
    validate_video_timestamps(video_timeline)
    validate_audio_timestamps(audio_timeline)
    validate_av_alignment(video, audio)
    sample_rate = int(audio["sample_rate"])
    channels = int(audio["channels"])
    if audio_contract is not None and (sample_rate != audio_contract.sample_rate
                                       or channels != audio_contract.channels):
        raise ValueError("audio sample rate or channel count differs")
    return {"bytes": path.stat().st_size, "sha256": sha256_file(path),
            "video_frames": video_timeline["frame_count"],
            "audio_frames": audio_timeline["frame_count"],
            "video_duration_s": float(video["duration"]),
            "audio_duration_s": float(audio["duration"]),
            "audio_start_s": float(audio["start_time"]),
            "audio_sample_rate": sample_rate,
            "audio_channels": channels,
            "audio_max_db": _audio_max_db(path),
            "audio_contract": ({"tier": "reported_only", "matched_supplied_contract": True,
                                "sample_rate": sample_rate, "channels": channels}
                               if audio_contract is not None
                               else {"tier": "unknown"}),
            "decoded_video_sha256": decoded_stream_sha256(path, "video"),
            "decoded_audio_sha256": decoded_stream_sha256(path, "audio"),
            "video_timeline_sha256": media_timeline_sha256(path, "video"),
            "audio_timeline_sha256": media_timeline_sha256(path, "audio")}


def validate_video_timestamps(timeline: dict[str, Any]) -> None:
    time_base = Fraction(timeline["stream"]["time_base"])
    seconds = [int(frame["best_effort_timestamp"]) * time_base
               for frame in timeline["frames"]]
    if not seconds or abs(seconds[0]) > Fraction(1, 24):
        raise ValueError("video timeline starts outside the expected boundary")
    if any(abs((right - left) - Fraction(1, 24)) > Fraction(1, 1000)
           for left, right in zip(seconds, seconds[1:])):
        raise ValueError("video timeline has shifted or irregular frame timestamps")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    baseline = actions.add_parser("baseline")
    baseline.add_argument("--output-root", type=Path, required=True)
    baseline.add_argument("--prefix", required=True)
    baseline.add_argument("--run-id")
    verify = actions.add_parser("verify")
    verify.add_argument("--output-root", type=Path, required=True)
    verify.add_argument("--history", type=Path, required=True)
    verify.add_argument("--prompt-id", required=True)
    verify.add_argument("--video-prefix", required=True)
    verify.add_argument("--latent-prefix", required=True)
    verify.add_argument("--video-baseline", type=Path, required=True)
    verify.add_argument("--latent-baseline", type=Path, required=True)
    verify.add_argument("--run-id")
    verify.add_argument("--audio-sample-rate", type=int)
    verify.add_argument("--audio-channels", type=int)
    args = parser.parse_args()
    try:
        if args.action == "baseline":
            result = prefix_baseline(args.output_root, args.prefix, args.run_id)
        else:
            if (args.audio_sample_rate is None) != (args.audio_channels is None):
                raise ValueError("audio sample rate and channels must be supplied together")
            contract = (AudioContract(args.audio_sample_rate, args.audio_channels)
                        if args.audio_sample_rate is not None else None)
            history = json.loads(args.history.read_text())
            video, latent = history_output_paths(
                history, args.prompt_id, args.output_root,
                args.video_prefix, args.latent_prefix,
                json.loads(args.video_baseline.read_text()),
                json.loads(args.latent_baseline.read_text()), args.run_id)
            video_result = inspect_video(video, contract)
            result = {"status": "SOURCE_MEDIA_CHECKED_CONTRACT_UNREVIEWED",
                      "prompt_id": args.prompt_id,
                      "video_path": str(video), "latent_path": str(latent),
                      "video": video_result, "latent": inspect_latent(latent)}
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, IndexError,
            json.JSONDecodeError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "INCOMPARABLE", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
