"""Validated creative controls for the bounded EP01 pilot."""
from __future__ import annotations

import math

from ep_pilot_timeline import Clip


def ending_video_filter(effect: dict | None, frames: int) -> str:
    if not effect:
        return ""
    first, last = effect["start_frame"], effect["end_frame"]
    zoom = effect["zoom"]
    if not (isinstance(first, int) and isinstance(last, int)
            and 0 <= first < last <= frames - 6):
        raise ValueError("ending push interval must finish before final fade")
    if not math.isfinite(zoom) or not 1 < zoom <= 1.10:
        raise ValueError("ending push zoom outside conservative bounds")
    ax, ay = effect.get("anchor_x", 0.5), effect.get("anchor_y", 0.5)
    if not all(math.isfinite(v) and 0 <= v <= 1 for v in (ax, ay)):
        raise ValueError("ending push anchor outside picture")
    progress = f"min(max((on-{first})/{last - first},0),1)"
    # Smoothstep avoids a sudden velocity change; 2x sampling reduces crop jitter.
    amount = f"({progress})*({progress})*(3-2*({progress}))"
    return (f"scale=1536:2752:flags=lanczos,"
            f"zoompan=z='1+{zoom - 1:.8f}*{amount}':"
            f"x='(iw-iw/zoom)*{ax}':y='(ih-ih/zoom)*{ay}':d=1:s=768x1376:fps=24")


def validate_protected_ranges(ranges: list[dict], clips: list[Clip]) -> None:
    for item in ranges:
        first, last = item["in_frame"], item["out_frame"]
        if not (isinstance(first, int) and isinstance(last, int) and 0 <= first < last):
            raise ValueError("invalid protected action interval")
        if not any(c.unit == item["unit"] and c.in_frame <= first < last <= c.out_frame
                   for c in clips):
            raise ValueError(f"edit removes protected action: {item}")


def cue_fades(cue: dict, total: float) -> tuple[float, float]:
    start, end = cue["start"], cue["end"]
    source_in = cue["source_in"]
    values = (start, end, source_in, cue.get("gain_offset_db", 0))
    if not all(math.isfinite(v) for v in values) or not 0 <= start < end <= total or source_in < 0:
        raise ValueError("invalid creative music cue")
    duration = end - start
    fade_in, fade_out = cue.get("fade_in", 1.2), cue.get("fade_out", 1.0)
    if not all(math.isfinite(v) and 0 <= v <= duration for v in (fade_in, fade_out)):
        raise ValueError("music fade outside cue duration")
    return fade_in, fade_out
