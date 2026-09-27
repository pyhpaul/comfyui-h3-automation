"""Codec and AV-latent checks for Test2 EP01's 15.083-second G4 units."""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

from h3_a100_media import decoded_stream_sha256
from h3_test2_ep01_contract import DURATION_SECONDS, FPS


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_latent_shapes(tensors: list[dict], expected_temporal: int | None = None) -> None:
    by_name = {item["name"]: item for item in tensors}
    if set(by_name) != {"audio", "video"}:
        raise RuntimeError("AV latent must contain exactly audio and video")
    audio, video = by_name["audio"], by_name["video"]
    a_shape, v_shape = audio["shape"], video["shape"]
    temporal = v_shape[2] if len(v_shape) == 5 else -1
    # U01 establishes the exact temporal shape; later units must match it.
    lower = math.floor(DURATION_SECONDS * 8)
    upper = math.ceil(DURATION_SECONDS * 8) + 2
    if (
        len(a_shape) != 4
        or a_shape[:3] != [1, 32, 2]
        or len(v_shape) != 5
        or v_shape[:2] != [1, 24]
        or v_shape[3:] != [86, 48]
        or not lower <= temporal <= upper
        or (expected_temporal is not None and temporal != expected_temporal)
        or not 40 * DURATION_SECONDS <= a_shape[3] <= 55 * DURATION_SECONDS
        or any(item["dtype"] != "torch.float32" or not item["finite"] for item in tensors)
    ):
        raise RuntimeError("Test2 AV latent shape, dtype or finite check failed")


def inspect_latent(path: Path, expected_temporal: int | None = None) -> dict:
    import torch
    from safetensors import safe_open

    tensors = []
    with safe_open(path, framework="pt", device="cpu") as opened:
        for name in opened.keys():
            tensor = opened.get_tensor(name)
            tensors.append({
                "name": name,
                "shape": list(tensor.shape),
                "dtype": str(tensor.dtype),
                "finite": bool(torch.isfinite(tensor).all().item()),
            })
    validate_latent_shapes(tensors, expected_temporal)
    return {"path": str(path), "bytes": path.stat().st_size,
            "sha256": sha256(path), "tensors": tensors}


def validate_video_metadata(media: dict) -> None:
    streams = media.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    duration = float(media["format"]["duration"])
    if (
        not video
        or not audio
        or video.get("codec_name") != "h264"
        or audio.get("codec_name") != "aac"
        or video.get("width") != 768
        or video.get("height") != 1376
        or video.get("r_frame_rate") != "24/1"
        or not DURATION_SECONDS <= duration <= DURATION_SECONDS + 1.0
        or abs(int(video.get("nb_frames", 0)) / FPS - duration) > 0.05
        or abs(float(video["duration"]) - float(audio["duration"])) > 0.05
        or abs(float(video["start_time"]) - float(audio["start_time"])) > 0.05
    ):
        raise RuntimeError(f"unexpected Test2 G4 media metadata: {media}")


def inspect_video(path: Path) -> dict:
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-show_entries", "stream=index,codec_type,codec_name,width,height,r_frame_rate,nb_frames,duration,start_time",
        "-of", "json", str(path),
    ], capture_output=True, text=True, timeout=60, check=True)
    media = json.loads(probe.stdout)
    validate_video_metadata(media)
    audio_probe = subprocess.run([
        "ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-i", str(path),
        "-vn", "-af", "volumedetect", "-f", "null", "-",
    ], capture_output=True, text=True, timeout=60, check=True)
    match = re.search(r"max_volume:\s*([\d.-]+) dB", audio_probe.stderr)
    if not match or float(match.group(1)) < -60:
        raise RuntimeError("Test2 G4 audio is silent or unexpectedly quiet")
    return {"path": str(path), "bytes": path.stat().st_size,
            "sha256": sha256(path), "probe": media,
            "audio_max_db": float(match.group(1)),
            "decoded_video_sha256": decoded_stream_sha256(path, "video"),
            "decoded_audio_sha256": decoded_stream_sha256(path, "audio")}
