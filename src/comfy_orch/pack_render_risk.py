"""Pre-queue render-risk scan for pack prompts (lihun/chaofu failure modes).

Wiring audit stays in ``prompt_wire``. This module only flags patterns that
historically caused failall / hard-cut junk — it does not rewrite prompts.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

_EN_DIALOGUE = re.compile(r"[（(]([^）)]*[A-Za-z][^）)]*)[）)]")
_SHORT_Q = re.compile(
    r"\b(Who|Whose|What|Why|Where|When|How|Mom|Dad|No|Yes|Ready|Wait|Stop)\b\s*[?!]?",
    re.I,
)
_OPEN_MOUTH = re.compile(
    r"(口型同步|开口|张嘴|说话|对白|台词|念出|说出|reads?|speaks?|says?|mouth(?:s)?\s+open)",
    re.I,
)
_CLOSED_MOUTH = re.compile(
    r"(闭口|闭嘴|双唇闭合|嘴唇闭合|不说话|无声|silent|lips?\s*closed|mouth(?:s)?\s*closed|does not speak)",
    re.I,
)
_TWO_SHOT = re.compile(
    r"(双人|两人|同框|纵深|另一[人名位]|over[\s-]?shoulder|two[\s-]?shot|both\s+(?:in\s+)?frame)",
    re.I,
)
_MULTI_NAME = re.compile(
    r"\b(Ava|Damian|Damien|Noah|Tessa|Ethan|Vivian|Brooks)\b",
    re.I,
)


@dataclass(frozen=True)
class RenderRisk:
    code: str  # A|B|C|D|E or DURATION
    severity: str  # HIGH|MED|LOW
    message: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def extract_en_dialogue_lines(prompt: str) -> list[str]:
    lines: list[str] = []
    for m in _EN_DIALOGUE.finditer(prompt):
        inner = " ".join(m.group(1).split()).strip()
        if inner and re.search(r"[A-Za-z]", inner):
            # skip pure labels
            if any(k in inner for k in ("身份", "母版", "参考")):
                continue
            lines.append(inner)
    return lines


def estimate_dialogue_duration_s(prompt: str, *, pad_s: float = 2.0) -> float:
    """Rough EN dialogue duration: ~2.7 words/s + pad. Floor 4s, cap 20s."""
    lines = extract_en_dialogue_lines(prompt)
    if not lines:
        return 0.0
    words = sum(len(re.findall(r"[A-Za-z0-9']+", ln)) for ln in lines)
    # short exclamations still need air
    speech = max(words / 2.7, 0.8 * len(lines))
    return float(min(20.0, max(4.0, speech + pad_s)))


def scan_render_risks(prompt: str, *, default_duration_s: float | None = 14.0) -> list[RenderRisk]:
    """Return ordered risks for one unit prompt_source / wired body."""
    text = prompt or ""
    lines = extract_en_dialogue_lines(text)
    risks: list[RenderRisk] = []

    has_open = bool(_OPEN_MOUTH.search(text))
    has_closed = bool(_CLOSED_MOUTH.search(text))
    two_shot = bool(_TWO_SHOT.search(text)) or len(set(_MULTI_NAME.findall(text))) >= 2

    # B: silent unit that still directs speech/open mouth
    if not lines and has_open and not has_closed:
        risks.append(
            RenderRisk(
                "B",
                "HIGH",
                "无对白（）却写开口/说话，且无闭口硬锁 → 易全程胡话；"
                "入队前加：画内人物全程闭口无声、禁止开口",
            )
        )

    # E: dual presence + dialogue without listener closed lock
    if lines and two_shot and not has_closed:
        risks.append(
            RenderRisk(
                "E",
                "HIGH",
                "疑似双人同框对白，缺听者闭口/无声硬锁 → 同念高风险；"
                "写清：说话者开口；画内其他人全程闭口无声；禁止同念",
            )
        )

    # C: very short question likely to be swallowed
    for ln in lines:
        words = re.findall(r"[A-Za-z0-9']+", ln)
        if len(words) <= 2 and _SHORT_Q.search(ln):
            risks.append(
                RenderRisk(
                    "C",
                    "MED",
                    f"极短问句 {ln!r} 易被吞进邻句；考虑独立镜头或加长边界",
                )
            )
            break

    # Duration fill → head/tail junk (A class upstream)
    if lines and default_duration_s is not None:
        need = estimate_dialogue_duration_s(text)
        if need > 0 and default_duration_s - need >= 4.0:
            risks.append(
                RenderRisk(
                    "DURATION",
                    "MED",
                    f"台词估时约 {need:.1f}s，默认时长 {default_duration_s:.1f}s，"
                    f"余量偏大易片头/片尾胡话；一采前用 apply_dialogue_duration 收紧",
                )
            )

    # D hint: names present without slow/clear cue (soft)
    if any(n.lower() in {"noah", "ava", "damian", "damien"} for n in _MULTI_NAME.findall(text)):
        if not re.search(r"(缓慢|清晰|enunciat|clear(?:ly)?|slow(?:ly)?)", text, re.I):
            if any(
                re.search(rf"\b{n}\b", " ".join(lines), re.I)
                for n in ("Noah", "Ava", "Damian", "Damien")
            ):
                risks.append(
                    RenderRisk(
                        "D",
                        "LOW",
                        "对白含易近音专名（Noah/Ava/Damian）；建议提示缓慢清晰读名",
                    )
                )

    return risks


def risks_as_warnings(risks: list[RenderRisk]) -> list[str]:
    return [f"render-risk [{r.severity}/{r.code}] {r.message}" for r in risks]


def high_risk_codes(risks: list[RenderRisk]) -> list[str]:
    return sorted({r.code for r in risks if r.severity == "HIGH"})
