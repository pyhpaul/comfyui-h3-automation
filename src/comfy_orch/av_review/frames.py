from __future__ import annotations

import hashlib
import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .media import Clip, MAX_BYTES, MediaError


MAX_FRAMES = 64
MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 12 * 1024 * 1024


@dataclass(frozen=True)
class Frame:
    path: Path
    time: float
    sha256: str


def validate_frame_budget(fps: float, duration: float) -> None:
    if (isinstance(fps, bool) or not isinstance(fps, (float, int)) or not math.isfinite(fps)
            or not 1 <= fps <= 8 or math.ceil(duration * fps) > MAX_FRAMES):
        raise MediaError("Grok screening requires fps 1-8 and at most 64 frames; use a shorter clip")


def extract_frames(clip: Clip, directory: Path, fps: float, *, start: float = 0.0,
                   end: float | None = None, native_resolution: bool = False) -> list[Frame]:
    end = clip.duration if end is None else end
    if (any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v)
            for v in (start, end)) or not 0 <= start < end <= clip.duration):
        raise MediaError("Frame window must be finite and inside the source clip")
    validate_frame_budget(fps, end-start)
    data = clip.path.read_bytes()
    if len(data) > MAX_BYTES or hashlib.sha256(data).hexdigest() != clip.sha256:
        raise MediaError("Source hash or size changed before frame extraction")
    snapshot = directory / "source.mp4"
    with snapshot.open("xb") as handle:
        handle.write(data)
    output = directory / "frames"
    output.mkdir(exist_ok=False)
    # Keep original presentation times, not synthetic FPS filter output times.
    filters = (f"setpts=PTS-STARTPTS,select='gte(t,{start})*lt(t,{end})*"
               f"(isnan(prev_selected_t)+gte(t-prev_selected_t,{1/fps}))',showinfo")
    if not native_resolution:
        filters += ",scale=768:768:force_original_aspect_ratio=decrease"
    command = ["ffmpeg", "-hide_banner", "-nostdin", "-n", "-protocol_whitelist", "file,pipe",
               "-f", "mov", "-i", str(snapshot), "-map", "0:v:0", "-an", "-vf", filters,
               "-fps_mode", "vfr", "-frames:v", str(MAX_FRAMES + 1), "-q:v", "3",
               str(output / "%03d.jpg")]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        raise MediaError("Local frame extraction failed; no provider request sent") from None
    times = [float(t) for t in re.findall(r"\bn:\s*\d+\s+pts:.*?pts_time:([\d.eE+-]+)", result.stderr)]
    files = sorted(output.glob("*.jpg"))
    if not 0 < len(files) <= MAX_FRAMES or len(files) != len(times):
        raise MediaError("Extracted frame count or timestamp evidence is invalid")
    sizes = [p.stat().st_size for p in files]
    if max(sizes) > MAX_IMAGE_BYTES or sum(sizes) > MAX_TOTAL_BYTES:
        raise MediaError("Extracted images exceed request size budget")
    if (any(not math.isfinite(t) or not 0 <= t < clip.duration for t in times)
            or any(b <= a for a, b in zip(times, times[1:]))):
        raise MediaError("Frame timestamps are not finite, ordered source-relative times")
    return [Frame(p, t, hashlib.sha256(p.read_bytes()).hexdigest()) for p, t in zip(files, times)]
