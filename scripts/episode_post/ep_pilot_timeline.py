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


_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven",
         "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
         "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
         "eighty", "ninety"]


def _number_words(value: int) -> list[str]:
    if value < 20:
        return [_ONES[value]]
    tens, ones = divmod(value, 10)
    return [_TENS[tens]] + ([_ONES[ones]] if ones else [])


def tokens(text: str, aliases: dict[str, str]) -> list[str]:
    # ASR often renders spoken numbers as digits ("35") while scripts spell
    # them out ("Thirty-five"); expand digit tokens so both sides compare
    # as the same word sequence. Aliases still win first. An alias value
    # may itself be several tokens ("noah" -> "no a") for names ASR splits
    # into separate words; it then expands to that sequence.
    result: list[str] = []
    for token in re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower()):
        token = aliases.get(token, token)
        # Whisper often emits "o" + "'clock" as two words; scripts keep o'clock.
        if token in {"o'clock", "oclock"}:
            result.extend(["o", "clock"])
            continue
        if token.isdigit():
            # Whisper often glues clock times ("39:30" → "3930"); expand as
            # mm+ss word sequences to match scripted "39:30" → thirty nine thirty.
            if len(token) in (3, 4):
                mm, ss = int(token[:-2]), int(token[-2:])
                if mm < 60 and ss < 60:
                    result.extend(_number_words(mm))
                    result.extend(_number_words(ss))
                    continue
            if int(token) < 100:
                result.extend(_number_words(int(token)))
                continue
        result.extend(token.split())
    return result


_WEAK_LEAD = frozenset({"i", "a", "oh", "uh", "um", "and", "but", "so"})


def _find_token_span(heard_tokens: list[str], need: list[str], cursor: int,
                     *, after: int | None = None) -> tuple[int, int] | None:
    """Return (start, need_len_used) for the best span match at/after cursor.

    Exact match first. If ASR dropped a weak leading pronoun/filler
    (e.g. scripted \"I wanted to.\" heard as \"wanted to.\"), retry without
    that lead token. Returns the heard span start and how many *heard*
    tokens were consumed (always len(matched need slice)).
    """
    start_at = cursor if after is None else after
    for drop in (0, 1):
        if drop and (len(need) < 2 or need[0] not in _WEAK_LEAD):
            break
        use = need[drop:]
        match = next((i for i in range(start_at, len(heard_tokens) - len(use) + 1)
                      if heard_tokens[i:i + len(use)] == use), None)
        if match is not None:
            return match, len(use)
    return None


def align_dialogue(lines: list[str], words: list[Word], aliases: dict[str, str],
                   skip_first: set[str] | None = None) -> list[Subtitle]:
    heard = [(token, word) for word in words for token in tokens(word.text, aliases)]
    heard_tokens = [token for token, _word in heard]
    cursor = 0
    cues: list[Subtitle] = []
    for line in lines:
        phrases = []
        for phrase in re.split(r"(?<=[.!?])\s+", line.strip()):
            # A single sentence too long for a two-line caption is shown as
            # consecutive clause cues; word order and timing still come from
            # the matched word track, only the display grouping changes.
            if len(phrase) > 42 and ", " in phrase:
                phrases.extend(p.strip() for p in
                               re.split(r"(?<=,)\s+", phrase) if p.strip())
            else:
                phrases.append(phrase)
        for phrase in phrases:
            need = tokens(phrase, aliases)
            if not need:
                continue
            found = _find_token_span(heard_tokens, need, cursor)
            if found is not None and skip_first and phrase in skip_first:
                # The plan deliberately keeps a later performance of this
                # phrase (the first is an editorial duplicate); align to
                # the next occurrence instead. Still an error if none.
                found = _find_token_span(
                    heard_tokens, need, cursor, after=found[0] + 1)
            if found is None:
                raise ValueError(f"cannot align scripted phrase: {phrase!r}")
            match, used = found
            first, last = heard[match][1], heard[match + used - 1][1]
            cues.append(Subtitle(first.unit, first.start, last.end, phrase))
            cursor = match + used
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
        if cue.text in endings:
            end = endings[cue.text]
        else:
            end = min(cue.end + 0.15, next_start - 0.03)
            if end < cue.end:
                # Back-to-back phrases (next sentence starts the frame this
                # one ends) cannot honour both the 0.15s hold and the gap
                # cap; let the cue end exactly at the next spoken start
                # instead of hiding its final words. Explicit overrides do
                # not get this fallback: they must not remove spoken words.
                end = cue.end
        if end < cue.end:
            raise ValueError("caption ending would hide spoken words")
        if end > next_start - 0.03 and end != cue.end:
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
