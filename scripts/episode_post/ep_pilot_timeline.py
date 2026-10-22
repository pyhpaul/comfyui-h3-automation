"""Pure frame timeline, ordered dialogue alignment and subtitle helpers."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re


@dataclass(frozen=True)
class Clip:
    unit: str
    in_frame: int
    out_frame: int


@dataclass(frozen=True)
class Subtitle:
    unit: str
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Word:
    unit: str
    start: float
    end: float
    text: str


def validate_clips(clips: list[Clip], frames: dict[str, int]) -> None:
    if not clips:
        raise ValueError("empty timeline interval list")
    used: dict[str, list[Clip]] = {}
    for clip in clips:
        if clip.in_frame < 0 or clip.out_frame <= clip.in_frame:
            raise ValueError(f"invalid interval: {clip}")
        if clip.unit not in frames or clip.out_frame > frames[clip.unit]:
            raise ValueError(f"source bounds exceeded: {clip}")
        for previous in used.get(clip.unit, []):
            if max(clip.in_frame, previous.in_frame) < min(clip.out_frame, previous.out_frame):
                raise ValueError(f"source overlap: {previous} and {clip}")
        used.setdefault(clip.unit, []).append(clip)


def remap_subtitles(cues: list[Subtitle], clips: list[Clip]) -> list[Subtitle]:
    mapped: list[Subtitle] = []
    matched: set[int] = set()
    offset = 0.0
    for clip in clips:
        start, end = clip.in_frame / 24, clip.out_frame / 24
        for i, cue in enumerate(cues):
            if cue.unit == clip.unit and start <= cue.start < cue.end <= end:
                mapped.append(Subtitle("EP01", offset + cue.start - start,
                                       offset + cue.end - start, cue.text))
                matched.add(i)
        offset += end - start
    if len(matched) != len(cues):
        raise ValueError("edit would drop or split required dialogue")
    return sorted(mapped, key=lambda cue: cue.start)


def tokens(text: str, aliases: dict[str, str]) -> list[str]:
    return [aliases.get(token, token)
            for token in re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower())]


def align_dialogue(lines: list[str], words: list[Word], aliases: dict[str, str]) -> list[Subtitle]:
    heard = [(token, word) for word in words for token in tokens(word.text, aliases)]
    heard_tokens = [token for token, _word in heard]
    cursor = 0
    cues: list[Subtitle] = []
    for line in lines:
        for phrase in re.split(r"(?<=[.!?])\s+", line.strip()):
            need = tokens(phrase, aliases)
            if not need:
                continue
            match = next((i for i in range(cursor, len(heard) - len(need) + 1)
                          if heard_tokens[i:i + len(need)] == need), None)
            if match is None:
                raise ValueError(f"cannot align scripted phrase: {phrase!r}")
            first, last = heard[match][1], heard[match + len(need) - 1][1]
            cues.append(Subtitle(first.unit, first.start, last.end, phrase))
            cursor = match + len(need)
    return cues


def verify_source(path: Path, expected: str) -> None:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"source hash mismatch: {path}")


def wrap_caption(text: str) -> str:
    if "\n" in text:
        if len(text.splitlines()) > 2 or max(map(len, text.splitlines())) > 36:
            raise ValueError("explicit caption line break exceeds layout bounds")
        return text
    if len(text) <= 36:
        return text
    words = text.split()
    choices = [(" ".join(words[:i]), " ".join(words[i:])) for i in range(1, len(words))]
    valid = [(a, b) for a, b in choices if max(len(a), len(b)) <= 36]
    if not valid:
        raise ValueError(f"caption needs more than two lines: {text!r}")
    first, second = min(valid, key=lambda pair: abs(len(pair[0]) - len(pair[1])))
    return first + "\n" + second


def presentation_cues(cues: list[Subtitle], style: dict) -> list[Subtitle]:
    endings = style.get("end_overrides", {})
    breaks = style.get("line_breaks", {})
    known = {cue.text for cue in cues}
    if (set(endings) | set(breaks)) - known:
        raise ValueError("caption override references unknown text")
    readable = []
    for i, cue in enumerate(cues):
        next_start = max(0, cues[i + 1].start - 0.04) if i + 1 < len(cues) else float("inf")
        end = endings.get(cue.text, min(cue.end + 0.15, next_start - 0.03))
        if end < cue.end:
            raise ValueError("caption ending would hide spoken words")
        if end > next_start - 0.03:
            raise ValueError("caption ending would overlap next speaker")
        text = breaks.get(cue.text, cue.text)
        if " ".join(text.split()) != " ".join(cue.text.split()):
            raise ValueError("caption line break changes dialogue text")
        readable.append(Subtitle(cue.unit, max(0, cue.start - 0.04), end, text))
    return readable


def timestamp(seconds: float) -> str:
    if seconds < 0:
        raise ValueError("negative subtitle timestamp")
    hours, remainder = divmod(round(seconds * 1000), 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def render_srt(cues: list[Subtitle]) -> str:
    return "".join(f"{i}\n{timestamp(cue.start)} --> {timestamp(cue.end)}\n"
                   f"{wrap_caption(cue.text)}\n\n"
                   for i, cue in enumerate(cues, 1))
