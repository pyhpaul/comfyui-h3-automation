"""Codec and AV-latent checks for Test2 EP01's 15.083-second G4 units."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from h3_a100_media import decoded_stream_sha256
from h3_test2_ep01_contract import DURATION_SECONDS, FPS, PARENTS


RAW_FRAMES = round(DURATION_SECONDS * FPS)
if RAW_FRAMES % 17 != 5:
    raise RuntimeError("Test2 duration is not on the H3 17k+5 frame grid")
VIDEO_LATENT_STEPS = ((RAW_FRAMES - 5) // 17) * 5 + 2
AUDIO_LATENT_STEPS = round(RAW_FRAMES / FPS * 40)
CONTEXT_TRIM_FRAMES = 22


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
    if (
        len(a_shape) != 4
        or a_shape != [1, 32, 2, AUDIO_LATENT_STEPS]
        or v_shape != [1, 24, VIDEO_LATENT_STEPS, 86, 48]
        or (expected_temporal is not None and v_shape[2] != expected_temporal)
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


def validate_video_metadata(media: dict, unit: str) -> None:
    if unit not in PARENTS:
        raise RuntimeError(f"unexpected Test2 unit: {unit}")
    expected_frames = RAW_FRAMES - (CONTEXT_TRIM_FRAMES if PARENTS[unit] else 0)
    expected_duration = expected_frames / FPS
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
        or int(video.get("nb_frames", 0)) != expected_frames
        or abs(duration - expected_duration) > 0.05
        or abs(float(video["duration"]) - expected_duration) > 0.05
        or abs(float(video["duration"]) - float(audio["duration"])) > 0.05
        or abs(float(video["start_time"]) - float(audio["start_time"])) > 0.05
    ):
        raise RuntimeError(f"unexpected Test2 G4 media metadata: {media}")


def inspect_video(path: Path, unit: str) -> dict:
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-show_entries", "stream=index,codec_type,codec_name,width,height,r_frame_rate,nb_frames,duration,start_time",
        "-of", "json", str(path),
    ], capture_output=True, text=True, timeout=60, check=True)
    media = json.loads(probe.stdout)
    validate_video_metadata(media, unit)
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
