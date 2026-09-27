"""Decoded-stream fingerprints independent of MP4 container metadata."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


def decoded_stream_sha256(path: Path, kind: str) -> str:
    if kind == "video":
        selector = ["-map", "0:v:0", "-c:v", "rawvideo", "-pix_fmt", "yuv420p"]
    elif kind == "audio":
        selector = ["-map", "0:a:0", "-c:a", "pcm_f32le"]
    else:
        raise ValueError(f"unsupported media stream: {kind}")
    command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
               "-threads", "1", "-i", str(path), *selector,
               "-f", "hash", "-hash", "SHA256", "-"]
    result = subprocess.run(command, capture_output=True, text=True,
                            timeout=120, check=True)
    digest = result.stdout.strip()
    if not re.fullmatch(r"SHA256=[0-9a-fA-F]{64}", digest):
        raise RuntimeError(f"unexpected {kind} decoded hash output: {digest!r}")
    return digest.partition("=")[2].lower()


def media_timeline(path: Path, kind: str) -> dict[str, object]:
    """Capture decoded-frame timing, independent of container labels."""
    if kind not in {"video", "audio"}:
        raise ValueError(f"unsupported media stream: {kind}")
    selector = "v:0" if kind == "video" else "a:0"
    command = [
        "ffprobe", "-v", "error", "-select_streams", selector,
        "-show_entries",
        "stream=codec_type,time_base,start_time,duration,avg_frame_rate,sample_rate,nb_frames:"
        "frame=media_type,best_effort_timestamp,pkt_duration,nb_samples",
        "-of", "json", str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True,
                            timeout=120, check=True)
    report = json.loads(result.stdout)
    streams = report.get("streams", [])
    if len(streams) != 1 or streams[0].get("codec_type") != kind:
        raise RuntimeError(f"expected one {kind} stream in {path}")
    frames = report.get("frames", [])
    if not frames or any(frame.get("media_type") != kind for frame in frames):
        raise RuntimeError(f"missing or mixed {kind} frames in {path}")
    if any("best_effort_timestamp" not in frame for frame in frames):
        raise RuntimeError(f"missing {kind} frame timestamps in {path}")
    return {"stream": streams[0], "frame_count": len(frames), "frames": frames}


def media_timeline_sha256(path: Path, kind: str) -> str:
    timeline = media_timeline(path, kind)
    canonical = json.dumps(timeline, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
