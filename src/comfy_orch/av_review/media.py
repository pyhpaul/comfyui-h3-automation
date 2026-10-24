from __future__ import annotations

import hashlib
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path


MAX_BYTES = 12 * 1024 * 1024
MAX_SECONDS = 30.0
MAX_SAMPLED_FRAMES = 240


class MediaError(ValueError):
    """Media failed local validation; do not send a provider request."""


@dataclass(frozen=True)
class Clip:
    path: Path
    sha256: str
    size: int
    duration: float
    has_audio: bool
    streams: list[dict]

    def public(self, project_root: Path) -> dict:
        return {
            "path": str(self.path.relative_to(project_root.resolve())),
            "sha256": self.sha256, "size_bytes": self.size,
            "duration_seconds": self.duration, "has_audio": self.has_audio,
            "streams": self.streams,
        }


def _allowed_path(project_root: Path, media_path: str) -> Path:
    path = Path(media_path)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    allowed = project_root.resolve() / "runs/visual_qc"
    if not path.is_relative_to(allowed):
        raise MediaError("Media must be inside the allowed runs/visual_qc directory")
    if path.suffix.lower() != ".mp4":
        raise MediaError("Only MP4 media is supported")
    if not path.is_file():
        raise MediaError("Media file does not exist")
    if not 0 < path.stat().st_size <= MAX_BYTES:
        raise MediaError("Media size must be between 1 byte and 12 MiB")
    return path


def inspect_clip(project_root: Path, media_path: str) -> Clip:
    path = _allowed_path(project_root, media_path)
    command = [
        "ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", "-f", "mov",
        "-show_entries", "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate,sample_rate,start_time",
        "-of", "json", str(path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=15)
        metadata = json.loads(result.stdout)
        duration = float(metadata["format"]["duration"])
        streams = metadata["streams"]
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        raise MediaError("Cannot inspect a valid local MP4 using ffprobe") from None
    if not math.isfinite(duration) or not 0 < duration <= MAX_SECONDS:
        raise MediaError("Media duration must be positive and at most 30 seconds")
    if not any(s.get("codec_type") == "video" for s in streams):
        raise MediaError("Media has no video stream")
    data = path.read_bytes()
    if len(data) > MAX_BYTES:
        raise MediaError("Media size changed beyond the permitted limit")
    return Clip(path, hashlib.sha256(data).hexdigest(), len(data), duration,
                any(s.get("codec_type") == "audio" for s in streams), streams)


def validate_sampling(fps: float, duration: float) -> None:
    if (isinstance(fps, bool) or not isinstance(fps, (int, float)) or not math.isfinite(fps)
            or not 1 <= fps <= 24 or math.ceil(fps * duration) > MAX_SAMPLED_FRAMES):
        raise MediaError("Requested fps must be 1-24 and at most 240 sampled frames per request")
