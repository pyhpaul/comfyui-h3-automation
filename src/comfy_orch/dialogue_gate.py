"""Score rendered speech against pack ``（）`` English lines before latent handoff."""
from __future__ import annotations

import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

_FULLWIDTH_LINE = re.compile(r"（\s*([A-Za-z0-9][^）]*?)\s*）")
_SILENT_MARKERS = (
    "本条没有任何对白",
    "本条无对白",
    "没有任何对白",
)

_NUMBER_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "twenty": "20",
    "thirty": "30",
    "forty": "40",
    "fifty": "50",
    "sixty": "60",
    "seventy": "70",
    "eighty": "80",
    "ninety": "90",
    "hundred": "100",
    "thousand": "1000",
}


@dataclass(frozen=True)
class ExpectedDialogue:
    lines: list[str]
    silent: bool


@dataclass(frozen=True)
class DialogueVerdict:
    ok: bool
    reason: str
    extras: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    overlap: float = 0.0


def extract_expected_dialogue(prompt_source: str) -> ExpectedDialogue:
    silent = any(m in prompt_source for m in _SILENT_MARKERS)
    lines: list[str] = []
    seen: set[str] = set()
    for match in _FULLWIDTH_LINE.finditer(prompt_source):
        text = match.group(1).strip()
        if not text or re.fullmatch(r"[\W_]+", text):
            continue
        key = _normalize(text)
        if key in seen:
            continue
        seen.add(key)
        lines.append(text)
    if silent:
        return ExpectedDialogue(lines=[], silent=True)
    return ExpectedDialogue(lines=lines, silent=False)


def _normalize(text: str) -> str:
    s = text.lower()
    s = s.replace("$", " ")
    s = s.replace("%", " percent ")
    # honorifics
    s = re.sub(r"\bms\.?\b", "miss", s)
    s = re.sub(r"\bmrs\.?\b", "missus", s)
    s = re.sub(r"\bmr\.?\b", "mister", s)
    # digit groups: 38,000 / 100,000
    s = re.sub(r"(\d),(\d{3})\b", r"\1\2", s)
    # wordy hundreds/thousands → digits (before single-word map, else
    # "seven hundred thousand" becomes "7 100 1000" and misses ASR "700000")
    _ones = (
        "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
        "thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
        "twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety"
    )
    s = s.replace("a hundred thousand", "100000")
    s = re.sub(
        rf"\b({_ones})\s+hundred\s+thousand\b",
        lambda m: str(int(_NUMBER_WORDS[m.group(1)]) * 100000),
        s,
    )
    s = s.replace("hundred thousand", "100000")

    def _tens_ones_thousand(m: re.Match[str]) -> str:
        return str((int(_NUMBER_WORDS[m.group(1)]) + int(_NUMBER_WORDS[m.group(2)])) * 1000)

    # thirty-eight thousand / thirty eight thousand before bare "eight thousand"
    s = re.sub(rf"\b({_ones})-({_ones})\s+thousand\b", _tens_ones_thousand, s)
    s = re.sub(rf"\b({_ones})\s+({_ones})\s+thousand\b", _tens_ones_thousand, s)
    s = re.sub(
        rf"\b({_ones})\s+hundred\b",
        lambda m: str(int(_NUMBER_WORDS[m.group(1)]) * 100),
        s,
    )
    s = re.sub(
        rf"\b({_ones})\s+thousand\b",
        lambda m: str(int(_NUMBER_WORDS[m.group(1)]) * 1000),
        s,
    )
    s = s.replace("fifty-thousand", "50000")
    s = re.sub(r"\b50k\b", "50000", s)
    s = re.sub(r"\b50\s*000\b", "50000", s)
    # ASR often emits "50 thousand" / "38 thousand"
    s = re.sub(
        r"\b(\d+)\s*thousand\b",
        lambda m: str(int(m.group(1)) * 1000),
        s,
    )
    for word, dig in _NUMBER_WORDS.items():
        s = re.sub(rf"\b{word}\b", dig, s)
    # 4.1 / $4.1 → "4 point 1" so ASR "four point one" covers expected digits
    s = re.sub(r"\b(\d+)\.(\d+)\b", r"\1 point \2", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _tokens(text: str) -> list[str]:
    return [t for t in _normalize(text).split() if t]


def _token_set(text: str) -> set[str]:
    return set(_tokens(text))


def _coverage(got: set[str], need: set[str]) -> float:
    if not need:
        return 1.0
    return len(got & need) / len(need)


def _segment_best_match(seg: str, expected_lines: Sequence[str]) -> float:
    st = _token_set(seg)
    if not st:
        return 0.0
    best = 0.0
    for line in expected_lines:
        et = _token_set(line)
        if not et:
            continue
        # how much of the segment is explained by this line
        best = max(best, len(st & et) / len(st))
    return best


def _leftover_junk_ratio(seg: str, expected_lines: Sequence[str]) -> float:
    """Fraction of segment tokens not covered by the union of expected lines."""
    st = _tokens(seg)
    if not st:
        return 0.0
    pool: set[str] = set()
    for line in expected_lines:
        pool |= _token_set(line)
    leftover = [t for t in st if t not in pool]
    return len(leftover) / len(st)


def score_transcript(
    *,
    heard: str,
    segments: Sequence[tuple[float, float, str]],
    expected: ExpectedDialogue,
    min_seg_match: float = 0.35,
    min_tail_match: float = 0.55,
    max_junk_ratio: float = 0.35,
) -> DialogueVerdict:
    if expected.silent:
        extras = [t for _a, _b, t in segments if len(_token_set(t)) >= 2]
        if extras or len(_token_set(heard)) >= 2:
            return DialogueVerdict(
                ok=False,
                reason="BAD_speech_on_silent",
                extras=extras or [heard.strip()],
                missing=[],
                overlap=0.0,
            )
        return DialogueVerdict(ok=True, reason="OK", extras=[], missing=[], overlap=1.0)

    exp_pool = _token_set(" ".join(expected.lines))
    heard_set = _token_set(heard)
    overlap = _coverage(heard_set, exp_pool) if exp_pool else 1.0

    missing = [
        line
        for line in expected.lines
        if _coverage(heard_set, _token_set(line)) < 0.5
    ]

    # Once every expected line is covered by prefix segments, later Whisper
    # segments on silent mouths are usually English hallucinations — ignore them.
    # Glued ad-lib in the covering segment (Roger Tardy) still scores as extra.
    cover_idx = -1
    if expected.lines:
        cum: set[str] = set()
        for i, (_a, _b, text) in enumerate(segments):
            cum |= _token_set(text)
            if all(_coverage(cum, _token_set(line)) >= 0.5 for line in expected.lines):
                cover_idx = i
                break
    score_n = len(segments) if cover_idx < 0 else cover_idx + 1

    extras: list[str] = []
    for i, (_a, _b, text) in enumerate(segments[:score_n]):
        if len(_token_set(text)) < 2:
            continue
        # Whisper often merges several short expected lines into one segment.
        # Flag only leftover tokens that are not explained by the expected pool
        # (Roger-Tardy style ad-lib), not low per-line match on a multi-line blob.
        junk = _leftover_junk_ratio(text, expected.lines)
        match = _segment_best_match(text, expected.lines)
        is_tail = i == score_n - 1
        if junk > max_junk_ratio:
            extras.append(text.strip())
        elif is_tail and match < min_tail_match and junk > 0.2:
            extras.append(text.strip())
        elif (not is_tail) and match < min_seg_match and junk > 0.25:
            extras.append(text.strip())

    if missing and extras:
        reason = "BAD_missing_extra"
    elif missing:
        reason = "BAD_missing"
    elif extras:
        reason = "BAD_extra"
    elif overlap < 0.75:
        reason = "BAD_low_overlap"
    else:
        reason = "OK"

    return DialogueVerdict(
        ok=reason == "OK",
        reason=reason,
        extras=extras,
        missing=missing,
        overlap=round(overlap, 2),
    )


def mp4_to_wav(mp4: Path, wav: Path) -> None:
    subprocess.check_call(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(mp4),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(wav),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


_whisper_model = None
_whisper_lock = threading.Lock()


def _get_whisper_model():
    """Lazy CPU Whisper singleton — constructing small each gate call wastes seconds."""
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    with _whisper_lock:
        if _whisper_model is not None:
            return _whisper_model
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError as exc:  # pragma: no cover - env dependent
            raise RuntimeError(
                "dialogue gate needs faster-whisper; install it or pass a custom transcribe fn"
            ) from exc
        _whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
        return _whisper_model


def transcribe_wav_faster_whisper(wav: Path) -> tuple[str, list[tuple[float, float, str]]]:
    model = _get_whisper_model()
    segs, _info = model.transcribe(
        str(wav), language="en", vad_filter=True, beam_size=5,
        condition_on_previous_text=False,
    )
    segments: list[tuple[float, float, str]] = []
    texts: list[str] = []
    for s in segs:
        t = (s.text or "").strip()
        if not t:
            continue
        segments.append((float(s.start), float(s.end), t))
        texts.append(t)
    return " ".join(texts), segments


TranscribeFn = Callable[[Path], tuple[str, list[tuple[float, float, str]]]]


def select_primary_mp4(paths: Sequence[Path]) -> Path | None:
    """Prefer pass1/audio mp4; otherwise first mp4."""
    mp4s = [p for p in paths if p.suffix.lower() == ".mp4"]
    if not mp4s:
        return None
    ranked = sorted(
        mp4s,
        key=lambda p: (
            0 if "pass1" in p.name.lower() or "一采" in p.name else 1,
            0 if "audio" in p.name.lower() else 1,
            p.name,
        ),
    )
    return ranked[0]


def check_mp4_dialogue(
    mp4: Path,
    prompt_source: str,
    *,
    transcribe: TranscribeFn | None = None,
) -> DialogueVerdict:
    """Extract audio, ASR, score against prompt_source expected lines."""
    expected = extract_expected_dialogue(prompt_source)
    with tempfile.TemporaryDirectory(prefix="h3-dlg-") as tmp:
        wav = Path(tmp) / "audio.wav"
        mp4_to_wav(mp4, wav)
        fn = transcribe or (lambda p: transcribe_wav_faster_whisper(p))
        heard, segments = fn(wav)
    return score_transcript(heard=heard, segments=segments, expected=expected)


def gate_enabled(flag: bool | None = None, env: str | None = None) -> bool:
    """Resolve CLI flag and ``H3_DIALOGUE_GATE`` env (1/true/yes)."""
    if flag is True:
        return True
    if flag is False:
        return False
    raw = (env if env is not None else __import__("os").environ.get("H3_DIALOGUE_GATE", "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def bump_noise_seed(workflow: dict, *, attempt: int) -> dict:
    """Copy workflow and offset every int seed so Comfy cannot cache retries.

    Attempt 1 leaves seeds unchanged. Attempt N>=2 adds ``(N-1) * large_prime`` so
    the graph hash differs and execution is not fully ``execution_cached``.
    Bumps RandomNoise and any other node int ``noise_seed`` / ``seed`` (e.g. KSampler).
    """
    import copy

    out = copy.deepcopy(workflow)
    if attempt <= 1:
        return out
    delta = (attempt - 1) * 1_000_003
    for node in out.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for key in ("noise_seed", "seed"):
            if key in inputs and isinstance(inputs[key], int):
                inputs[key] = int(inputs[key]) + delta
    return out
