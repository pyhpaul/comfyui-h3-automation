"""H3 manual call pack (manifest.csv + EPxx/*.txt + shared assets/).

Supports:
- v3: 「仅复制进 H3的模型输入文本」 + skip pending controls
- v8/v2.1: 【画面总约束】+【逐镜执行】; bracket asset lines ``- [id]``
- v11/v2.1: same model body; numbered asset lines ``1. Name（id）｜…``
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from comfy_orch.ep_pack import UnitMediaPlan
from comfy_orch.errors import ValidationError

_PACK_KIND = "h3_manual_call"
_DURATION = re.compile(r"时长[：:]\s*(\d+)\s*s", re.I)
_DURATION_V21 = re.compile(r"目标时长[：:]\s*(\d+(?:\.\d+)?)\s*秒")
# v3/v8: - [char-002] …
_ASSET_LINE_BRACKET = re.compile(r"^- \[([^\]]+)\]\s*(.+)$")
# v11: 1. Mia · …（char-002）｜…
_ASSET_LINE_NUMBERED = re.compile(
    r"^\d+\.\s+.+\（([A-Za-z0-9\-]+)\）\s*(.*)$"
)
_PACK_REL = re.compile(r"包内路径[：:]([^\s｜|]+)")
_AT_PIC = re.compile(r"@图片(\d+)")
_MODEL_HEADER = "## 仅复制进 H3 的模型输入文本"
_V21_CONSTRAINT = "【画面总约束】"
_V21_HANDOFF = "【交出状态】"


@dataclass(frozen=True)
class ManualAsset:
    asset_id: str
    pack_rel: str
    is_control: bool
    uploadable: bool


@dataclass
class ParsedManualUnit:
    duration_seconds: int
    uploadable: list[ManualAsset]
    dropped_control_ids: list[str] = field(default_factory=list)
    model_prompt: str = ""
    picture_to_asset: dict[int, str] = field(default_factory=dict)
    layout: str = "v3_copy_section"


def is_h3_manual_call_pack(pack_root: Path) -> bool:
    root = pack_root.resolve()
    return (
        (root / "manifest.csv").is_file()
        and (root / "assets").is_dir()
        and any((root / ep).is_dir() for ep in ("EP01", "EP02", "EP03"))
        and not (root / "upload-manifest.json").is_file()
        and not (root / "manifest.json").is_file()
    )


def list_manual_unit_ids(pack_root: Path, *, episode: str | None = None) -> list[str]:
    rows = _read_manifest(pack_root.resolve())
    out: list[str] = []
    for row in rows:
        ep = (row.get("Episode") or "").strip()
        uid = (row.get("U") or "").strip()
        if not uid:
            continue
        if episode and ep.upper() != episode.upper():
            continue
        out.append(uid)
    return out


def _read_manifest(pack_root: Path) -> list[dict[str, str]]:
    path = pack_root / "manifest.csv"
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _episode_for_unit(unit_id: str) -> str:
    m = re.match(r"(ep\d+)-", unit_id, re.I)
    if not m:
        raise ValidationError(f"cannot infer episode from unit id: {unit_id}")
    return m.group(1).upper()


def _extract_model_prompt(text: str) -> tuple[str, str]:
    """Return (model_prompt, layout_tag)."""
    if _MODEL_HEADER in text:
        model = text.split(_MODEL_HEADER, 1)[1].strip()
        if model.startswith("##"):
            model = ""
        if len(model) < 20:
            raise ValidationError("model input section is empty or too short")
        return model, "v3_copy_section"

    if _V21_CONSTRAINT in text:
        body = text.split(_V21_CONSTRAINT, 1)[1]
        if _V21_HANDOFF in body:
            body = body.split(_V21_HANDOFF, 1)[0]
        # Drop any accidental latent/tail headers if present before handoff
        for stop in (
            "## TXT 尾部",
            "【H3 latent",
            "【测试提交规则】",
        ):
            if stop in body:
                body = body.split(stop, 1)[0]
        model = (_V21_CONSTRAINT + body).strip()
        if len(model) < 40:
            raise ValidationError("v2.1 model body (约束+逐镜) is empty or too short")
        if "@图片" not in model:
            raise ValidationError("v2.1 model body missing @图片 mapping lines")
        return model, "v21_constraint_shots"

    raise ValidationError("missing model input section")


def _control_is_pending(rest: str) -> bool:
    # 「仅供老板手动上传」 must not match 「不可上传」
    if "规格待生成" in rest or "待生成" in rest:
        return True
    if "不可上传" in rest and "手动上传" not in rest:
        return True
    return False


def _iter_asset_entries(text: str) -> list[tuple[str, str]]:
    """Yield (asset_id, rest) from bracket or numbered upload lines."""
    out: list[tuple[str, str]] = []
    for line in text.splitlines():
        s = line.strip()
        am = _ASSET_LINE_BRACKET.match(s) or _ASSET_LINE_NUMBERED.match(s)
        if not am:
            continue
        out.append((am.group(1), am.group(2)))
    return out


def parse_manual_unit_txt(text: str) -> ParsedManualUnit:
    duration = 10
    m = _DURATION_V21.search(text) or _DURATION.search(text)
    if m:
        duration = int(float(m.group(1)))

    uploadable: list[ManualAsset] = []
    dropped: list[str] = []
    picture_to_asset: dict[int, str] = {}

    for n, aid in re.findall(r"@图片(\d+)=([A-Za-z0-9\-]+)", text):
        picture_to_asset[int(n)] = aid

    for asset_id, rest in _iter_asset_entries(text):
        is_control = asset_id.startswith("ctrl-") or "控制图" in rest
        rel_m = _PACK_REL.search(rest)
        rel = rel_m.group(1).replace("\\", "/") if rel_m else ""
        if rel == "不适用":
            rel = ""
        if is_control and (_control_is_pending(rest) or not rel):
            dropped.append(asset_id)
            continue
        if "文件存在" in rest and rel:
            uploadable.append(
                ManualAsset(
                    asset_id=asset_id,
                    pack_rel=rel,
                    is_control=is_control,
                    uploadable=True,
                )
            )

    model, layout = _extract_model_prompt(text)

    return ParsedManualUnit(
        duration_seconds=duration,
        uploadable=uploadable,
        dropped_control_ids=dropped,
        model_prompt=model,
        picture_to_asset=picture_to_asset,
        layout=layout,
    )


def _ctrl_picture_indices(parsed: ParsedManualUnit) -> set[int]:
    """Indices to drop from the model body — only pending/skipped controls.

    Uploadable control images (v8/v2.1) keep their @图片N → <Picture N> wiring.
    """
    dropped = set(parsed.dropped_control_ids)
    out: set[int] = set()
    for n, aid in parsed.picture_to_asset.items():
        if aid in dropped:
            out.add(n)
    # Fallback when TXT has no @图片N=asset table: drop @图片 beyond uploadable count
    if not out and dropped:
        nums = [int(x) for x in _AT_PIC.findall(parsed.model_prompt)]
        if nums:
            max_up = len(parsed.uploadable)
            out = {n for n in nums if n > max_up}
    return out


def wire_manual_model_prompt(
    model_prompt: str,
    *,
    uploadable_count: int,
    drop_picture_indices: set[int] | None = None,
) -> str:
    """Drop control @图片 sentences; map remaining @图片N → <Picture N> (stable ids)."""
    drop = set(drop_picture_indices or ())
    text = _drop_at_picture_sentences(model_prompt, drop) if drop else model_prompt.strip() + "\n"

    def _sub(m: re.Match[str]) -> str:
        n = int(m.group(1))
        if 1 <= n <= uploadable_count:
            return f"<Picture {n}>"
        return m.group(0)

    text = _AT_PIC.sub(_sub, text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def plan_manual_unit(pack_root: Path, unit_id: str) -> UnitMediaPlan:
    pack_root = pack_root.resolve()
    unit_id = unit_id.strip()
    ep = _episode_for_unit(unit_id)
    prompt_rel = f"{ep}/{unit_id}.txt"
    path = pack_root / prompt_rel
    if not path.is_file():
        raise ValidationError(f"missing prompt: {prompt_rel}")

    # Ensure unit is listed when manifest present
    ids = list_manual_unit_ids(pack_root)
    if unit_id not in ids:
        raise ValidationError(f"unit not found in manifest.csv: {unit_id}")

    parsed = parse_manual_unit_txt(path.read_text(encoding="utf-8"))
    if not parsed.uploadable:
        raise ValidationError(f"{unit_id}: no uploadable stills after dropping controls")
    if len(parsed.uploadable) > 6:
        raise ValidationError(
            f"{unit_id}: {len(parsed.uploadable)} stills exceed YZ ref_image_0..5"
        )
    for asset in parsed.uploadable:
        if not (pack_root / asset.pack_rel).is_file():
            raise ValidationError(f"{unit_id}: missing asset {asset.pack_rel}")

    return UnitMediaPlan(
        unit_id=unit_id,
        control=None,
        previz=None,
        identities=[a.pack_rel for a in parsed.uploadable],
        prompt_rel=prompt_rel,
        duration_seconds=parsed.duration_seconds,
        pack_kind=_PACK_KIND,
    )


def build_manual_prompts(pack_root: Path, unit_id: str) -> tuple[str, str]:
    """prompt_source (@图片, ctrl dropped) and prompt_h3 (<Picture>)."""
    plan = plan_manual_unit(pack_root, unit_id)
    raw = (pack_root / plan.prompt_rel).read_text(encoding="utf-8")
    parsed = parse_manual_unit_txt(raw)
    drop = _ctrl_picture_indices(parsed)
    n = len(parsed.uploadable)
    source = _drop_at_picture_sentences(parsed.model_prompt, drop)
    wired = wire_manual_model_prompt(
        source,
        uploadable_count=n,
        drop_picture_indices=set(),
    )
    return source, wired


def _drop_at_picture_sentences(model_prompt: str, drop: set[int]) -> str:
    if not drop:
        return model_prompt.strip() + "\n"
    lines = model_prompt.strip().splitlines()
    if not lines or "@图片" not in lines[0]:
        kept_lines = []
        for ln in lines:
            m = _AT_PIC.match(ln.strip())
            if m and int(m.group(1)) in drop:
                continue
            kept_lines.append(ln)
        return "\n".join(kept_lines).strip() + "\n"

    head = lines[0]
    parts = re.findall(r"@图片\d+[^@]*", head)
    kept = [
        p
        for p in parts
        if not ((m := _AT_PIC.match(p)) and int(m.group(1)) in drop)
    ]
    suffix_m = re.search(r"(?:@图片\d+[^@]*)+$", head)
    suffix = head[suffix_m.end() :].strip() if suffix_m else ""
    prefix = head[: head.find("@图片")].strip()
    new_head = ((prefix + " ") if prefix else "") + "".join(kept)
    if suffix:
        if not new_head.endswith(("。", " ", "\n")):
            new_head += " "
        new_head += suffix
    lines[0] = new_head.strip()
    return "\n".join(lines).strip() + "\n"


_SPEECH_SAY = re.compile(
    r"(?P<lead>[^。\n]{0,24}?)说[：:]\s*(?P<line>\{[^}]+\})"
)
_TIMING_BRACKET = re.compile(r"〔[^〕]*〕")
_TIMING_PAREN = re.compile(r"[（(]本条最长[^）)]*[）)]")

_HARD_RULES = (
    "AUDIO/TEXT HARD RULES: The ONLY allowed speech is English inside braces {}. "
    "Never speak Chinese. Never narrate stage directions, camera notes, timing notes, "
    "or phrases like shot length / 'longest shot'. Silent except brace dialogue. "
    "Never render Chinese characters, subtitles, captions, lyrics, karaoke, UI text, "
    "or any on-screen glyphs/watermarks. Mouth motion only for the English speaker."
)


def suppress_on_screen_chinese_leak(prompt: str) -> str:
    """Reduce Chinese dialogue/subtitle/VO leakage while keeping shot body text.

    - Rewrites ``…说：{English}`` cues into an explicit English-only speech cue
    - Strips 〔…〕 / timing meta notes (often read aloud by H3)
    - Appends hard no-Chinese-speech / no-on-screen-text rules
    """
    text = prompt.strip()

    def _repl(m: re.Match[str]) -> str:
        lead = m.group("lead") or ""
        lead = re.sub(
            r"(?:压着火|气短地|低而稳地|职业化且冷地|冷地|稳地)$",
            "",
            lead,
        )
        return f"{lead}speaks English only (never Chinese): {m.group('line')}"

    text = _SPEECH_SAY.sub(_repl, text)
    text = _TIMING_BRACKET.sub("", text)
    text = _TIMING_PAREN.sub("", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" *。\s*。", "。", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.replace(
        "无字幕、无水印、无额外人物",
        "无字幕、无烧屏中文字、无旁白念镜注、无水印、无额外人物",
    )
    text = text.replace(
        "无字幕、无烧屏中文字、无水印、无额外人物",
        "无字幕、无烧屏中文字、无旁白念镜注、无水印、无额外人物",
    )
    if "AUDIO/TEXT HARD RULES:" in text:
        text = text.split("AUDIO/TEXT HARD RULES:")[0].rstrip()
    text = text.rstrip() + "\n\n" + _HARD_RULES
    return text.strip() + "\n"
