from __future__ import annotations

import re
from pathlib import Path

_WIN_OR_REL_ASSET = re.compile(
    r"(?:[A-Za-z]:[\\/][^\n]*?[\\/])?(?:assets|images)[\\/](?:characters|props|scenes)[\\/]([^\s\\/]+?\.(?:png|jpe?g|webp))",
    re.I,
)
# Pack-relative without assets/ prefix: characters/char-002.png
_PACK_REL_ASSET = re.compile(
    r"(?<![A-Za-z0-9_/-])(?:characters|props|scenes)[\\/]([^\s\\/]+?\.(?:png|jpe?g|webp))",
    re.I,
)
# Seedance-style / JARVIS Production refs: @char-002 @prop-001 @scene-001
_AT_ASSET = re.compile(r"@(char|prop|scene)-([A-Za-z0-9._-]+)\b", re.I)
_PICTURE = re.compile(r"<Picture\s+(\d+)>")
_VIDEO = re.compile(r"<Video\s+(\d+)>")

# Parent-input phrases only. Do NOT include bare "原始 H3 AV latent" — that also
# appears in 提交规则 ("保存原始 H3 AV latent") and must stay pack text.
_PARENT_LATENT_PHRASES = (
    "上一 U 的原始 H3 AV latent",
    "本测试包新生成上一 U 的原始 latent",
    "本测试包新 U01 的原始 H3 AV latent",
    "本测试包新 U02 的原始 H3 AV latent",
    "本测试包新 U03 的原始 H3 AV latent",
    "本测试包新 U04 的原始 H3 AV latent",
    "本测试包新 U05 的原始 H3 AV latent",
    "本测试包新 U06 的原始 H3 AV latent",
)
_PARENT_VIDEO_LABEL = "父片段：<Video 1>"


def _bare_name(path: str) -> str:
    name = Path(path).name
    name = re.sub(r"^id\d+-", "", name, flags=re.I)
    name = re.sub(r"^(control|previz|parent)-", "", name, flags=re.I)
    return name


def _image_slots(field_paths: dict[str, str]) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for i in range(0, 8):
        key = f"ref_image_{i}"
        if key in field_paths:
            out.append((i, field_paths[key]))
    return out


def wire_pack_prompt(prompt: str, field_paths: dict[str, str]) -> str:
    """Replace only media path/name tokens with <Picture N>/<Video 1>.

    Leaves all other pack text unchanged (Chinese/English body, structure, rules).
    """
    out = prompt
    # Longest/most specific first: full Windows-style asset paths keyed by basename.
    basename_to_picture: dict[str, str] = {}
    for order, (_idx, path) in enumerate(_image_slots(field_paths), start=1):
        bare = _bare_name(path).lower()
        basename_to_picture[bare] = f"<Picture {order}>"

    def _asset_sub(m: re.Match[str]) -> str:
        bare = m.group(1).lower()
        return basename_to_picture.get(bare, m.group(0))

    out = _WIN_OR_REL_ASSET.sub(_asset_sub, out)
    out = _PACK_REL_ASSET.sub(_asset_sub, out)

    # Any leftover Windows absolute asset paths → pack-relative assets/...
    # (for listed assets not bound to a Picture slot, e.g. U07 7th still)
    out = re.sub(
        r"[A-Za-z]:[\\/][^\n]*?[\\/](assets[\\/](?:characters|props|scenes)[\\/][^\s\\/]+?\.(?:png|jpe?g|webp))",
        lambda m: m.group(1).replace("\\", "/"),
        out,
        flags=re.I,
    )

    # @char-002 / @prop-001 / @scene-001 → <Picture N> (stem match to bound stills)
    stem_to_picture: dict[str, str] = {}
    for order, (_idx, path) in enumerate(_image_slots(field_paths), start=1):
        stem = Path(_bare_name(path)).stem.lower()
        if stem:
            stem_to_picture[stem] = f"<Picture {order}>"

    def _at_sub(m: re.Match[str]) -> str:
        token = f"{m.group(1)}-{m.group(2)}".lower()
        if token in stem_to_picture:
            return stem_to_picture[token]
        # named-asset files: @char-013 → char-013-agent-alden.png
        hits = [
            stem
            for stem in stem_to_picture
            if stem == token or stem.startswith(f"{token}-")
        ]
        if not hits:
            return m.group(0)
        hits.sort(key=len, reverse=True)
        return stem_to_picture[hits[0]]

    out = _AT_ASSET.sub(_at_sub, out)

    # staged job filenames / bare names left in text
    for order, (_idx, path) in enumerate(_image_slots(field_paths), start=1):
        label = f"<Picture {order}>"
        name = Path(path).name
        bare = _bare_name(path)
        for token in (name, bare):
            if token and token not in label:
                out = re.sub(re.escape(token), label, out, flags=re.I)

    if "ref_video_0" in field_paths:
        vpath = field_paths["ref_video_0"]
        vname = Path(vpath).name
        out = re.sub(re.escape(vname), "<Video 1>", out, flags=re.I)
        bare_v = _bare_name(vpath)
        if bare_v and bare_v != vname:
            out = re.sub(re.escape(bare_v), "<Video 1>", out, flags=re.I)
        for phrase in _PARENT_LATENT_PHRASES:
            out = out.replace(phrase, "<Video 1>")
        # Pack 接入文字 is narrative-only (no video path). Bind parent slot with a
        # single media label so H3 sees <Video 1> without rewriting shot text.
        if "<Video 1>" not in out:
            marker = "【H3 latent 接入文字】\n"
            if marker in out:
                out = out.replace(marker, f"{marker}{_PARENT_VIDEO_LABEL}\n", 1)
            else:
                out = f"{_PARENT_VIDEO_LABEL}\n{out}"

    return out


def _strip_media_tokens(text: str) -> str:
    text = _PICTURE.sub("", text)
    text = _VIDEO.sub("", text)
    text = re.sub(r"@图片\d+", "", text)
    text = _AT_ASSET.sub("", text)
    text = _WIN_OR_REL_ASSET.sub("", text)
    text = _PACK_REL_ASSET.sub("", text)
    text = re.sub(r"\bid\d+-[\w.-]+\.(?:png|jpe?g|webp|mp4|webm)\b", "", text, flags=re.I)
    text = re.sub(r"\bparent_prev\.mp4\b", "", text, flags=re.I)
    for phrase in _PARENT_LATENT_PHRASES:
        text = text.replace(phrase, "")
    text = text.replace("父片段：", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text


def _body_for_audit(text: str) -> str:
    """Media-stripped body with blank lines dropped for stable compare."""
    lines = [ln.rstrip() for ln in _strip_media_tokens(text).splitlines() if ln.strip()]
    return "\n".join(lines)


def audit_pack_prompt_wiring(
    source: str,
    wired: str,
    field_paths: dict[str, str],
) -> list[str]:
    """Audit that wiring only changed media names/paths. Empty list = pass."""
    violations: list[str] = []
    if not source.strip():
        violations.append("source prompt is empty")
        return violations
    if source == wired and _image_slots(field_paths):
        # May still be ok if pack already used Picture labels; check labels exist.
        pass

    src_body = _body_for_audit(source)
    wired_body = _body_for_audit(wired)
    if src_body != wired_body:
        violations.append(
            "non-media content changed between source and wired prompt "
            "(audit failed: only Picture/Video path replacement is allowed)"
        )

    n_img = len(_image_slots(field_paths))
    for i in range(1, n_img + 1):
        if f"<Picture {i}>" not in wired:
            violations.append(f"missing <Picture {i}> after wiring")

    if "ref_video_0" in field_paths and "<Video 1>" not in wired:
        violations.append("ref_video_0 present but <Video 1> not found in wired prompt")

    # Must not leave Windows absolute deliverable paths.
    if re.search(r"[A-Za-z]:\\[^\n]*\\(?:assets|images)\\", wired):
        violations.append("Windows absolute asset paths remain in wired prompt")

    # Parent wiring must not rewrite the pack's save-latent submit rule.
    if "保存原始 H3 AV latent" in source and "保存原始 H3 AV latent" not in wired:
        violations.append("submit rule '保存原始 H3 AV latent' was altered by wiring")
    if "保存<Video 1>" in wired:
        violations.append("submit rule incorrectly rewired to '保存<Video 1>'")

    return violations


_CLOSEUP_MARKERS = ("特写", "极近", "微距", "极特写")
_EN_DIALOGUE_LOCK = re.compile(
    r"(只能读[（(][）)]内的英文|only\s+read\s+English\s+in\s+[（(][）)]|"
    r"人物对白只能读)",
    re.I,
)
_CJK = re.compile(r"[\u4e00-\u9fff]")
_PIC1_BIND_LABEL = re.compile(
    r"<Picture\s+1>\s*[（(]([^）)]+)[）)]",
    re.I,
)
_SHOT1_BLOCK = re.compile(
    r"(【镜头\s*1[^】]*】)([\s\S]*?)(?=【镜头\s*2|【H3|###\s*【|$)",
    re.I,
)
_LATIN_NAME = re.compile(r"\b([A-Z][a-z]+(?:-[A-Z][a-z]+)?)\b")
_FALSE_NAMES = frozenset(
    {
        "picture",
        "video",
        "subject",
        "shot",
        "ep",
        "vo",
        "os",
        "ui",
        "av",
        "h3",
        "yz",
        "english",
        "live",
        "action",
    }
)


def _char_image_slots(field_paths: dict[str, str]) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for idx, path in _image_slots(field_paths):
        bare = _bare_name(path).lower()
        if bare.startswith("char-") or "-char-" in bare:
            out.append((idx, path))
    return out


def _first_latin_name(text: str) -> str | None:
    for name in _LATIN_NAME.findall(text):
        if name.casefold() in _FALSE_NAMES:
            continue
        return name
    return None


def _picture1_identity_name(wired: str) -> str | None:
    m = _PIC1_BIND_LABEL.search(wired)
    if m:
        label = m.group(1)
        latin = _first_latin_name(label)
        if latin:
            return latin
        if "身份" in label or "母版" in label:
            return label.split()[0][:32]
    for line in wired.splitlines():
        if not re.search(r"(?:角色参考|主母版)\s*[:：]?\s*<Picture\s+1>", line, re.I):
            if not re.search(r"主母版[^<\n]{0,20}<Picture\s+1>", line):
                if not re.search(r"角色参考\s*<Picture\s+1>", line, re.I):
                    continue
        latin = _first_latin_name(line)
        if latin:
            return latin
    m = re.search(
        r"([A-Za-z][A-Za-z'-]{1,40})\s*主母版[\s\S]{0,40}<Picture\s+1>",
        wired,
        re.I,
    )
    if m and m.group(1).casefold() not in _FALSE_NAMES:
        return m.group(1)
    return None


def _picture1_used_as_identity(wired: str) -> bool:
    if _PIC1_BIND_LABEL.search(wired) and re.search(
        r"<Picture\s+1>\s*[（(][^）)]*(身份|母版)", wired, re.I
    ):
        return True
    if re.search(r"角色参考\s*<Picture\s+1>|<Picture\s+1>\s*[：:].{0,12}角色", wired, re.I):
        return True
    if re.search(r"主母版[^。\n]{0,20}<Picture\s+1>", wired):
        return True
    return False


def _shot1_lead_name(wired: str) -> tuple[str | None, bool]:
    m = _SHOT1_BLOCK.search(wired)
    if not m:
        return None, False
    header, body = m.group(1), m.group(2)
    closeup = any(tok in header for tok in _CLOSEUP_MARKERS)
    cleaned = re.sub(r"<[^>]+>", " ", body)
    return _first_latin_name(cleaned), closeup


def _chinese_paren_tts_warnings(wired: str) -> list[str]:
    if not _EN_DIALOGUE_LOCK.search(wired):
        return []
    warnings: list[str] = []
    for m in re.finditer(r"[（(]([^）)]{1,80})[）)]", wired):
        inner = m.group(1)
        if _CJK.search(inner) and not re.fullmatch(r"[A-Za-z0-9\s'.,!?…\-]+", inner):
            # Identity/bind labels in Chinese parens are TTS bait under EN-only lock.
            if any(k in inner for k in ("身份", "母版", "参考", "主图", "空间")):
                warnings.append(
                    "Chinese label inside （） under English-dialogue-only lock: "
                    f"（{inner[:40]}）"
                )
                break
    return warnings


def audit_pack_prompt_semantics(
    wired: str,
    field_paths: dict[str, str],
) -> tuple[list[str], list[str]]:
    """Semantic gate beyond wire integrity.

    Returns ``(violations, warnings)``.
    Elevated: ``<Picture 1>`` is treated as a character identity while Shot 1
    closeup lead is a different named character (YZ control-slot conflict).
    """
    violations: list[str] = []
    warnings: list[str] = []

    char_slots = _char_image_slots(field_paths)
    p1_is_char = any(idx == 0 for idx, _ in char_slots)
    p1_as_identity = _picture1_used_as_identity(wired)
    p1_name = _picture1_identity_name(wired)
    shot_lead, shot_closeup = _shot1_lead_name(wired)

    if p1_is_char and p1_as_identity and len(char_slots) >= 2:
        warnings.append(
            "Picture 1 is wired as character identity while YZ ref_image_0 is "
            "the control slot; prefer control/blocking still or lead-matching identity"
        )

    if (
        p1_name
        and shot_lead
        and shot_closeup
        and p1_name.casefold() != shot_lead.casefold()
        and len(char_slots) >= 2
    ):
        msg = (
            f"Picture 1 identity focus mismatch: Picture 1≈{p1_name}, "
            f"Shot1 closeup lead≈{shot_lead}"
        )
        violations.append(msg)

    warnings.extend(_chinese_paren_tts_warnings(wired))
    return violations, warnings


def unbound_relative_assets(wired: str) -> list[str]:
    """Relative pack assets left in wired text (e.g. U07 7th still with no slot)."""
    return re.findall(
        r"assets/(?:characters|props|scenes)/[^\s]+\.(?:png|jpe?g|webp)",
        wired,
        flags=re.I,
    )


def preflight_pack_prompt(
    source: str,
    field_paths: dict[str, str],
    *,
    simulate_parent: bool = False,
    parent_rel: str = "assets/parent_prev.mp4",
) -> dict[str, object]:
    """Wire + audit one unit. Optionally simulate serial parent video binding.

    Returns a report dict. ``ok`` is True only when violations is empty.
    ``warnings`` may list unbound relative assets (non-fatal).
    """
    fields = dict(field_paths)
    if simulate_parent:
        fields["ref_video_0"] = parent_rel
    else:
        fields.pop("ref_video_0", None)
    if "@图片" in source:
        from comfy_orch.manual_call_pack import wire_manual_model_prompt

        n_img = len(_image_slots(fields))
        wired = wire_manual_model_prompt(
            source,
            uploadable_count=n_img,
            drop_picture_indices=set(),
        )
        if "ref_video_0" in fields and "<Video 1>" not in wired:
            wired = f"父片段：<Video 1>\n{wired}"
    else:
        wired = wire_pack_prompt(source, fields)
    violations = audit_pack_prompt_wiring(source, wired, fields)
    sem_violations, sem_warnings = audit_pack_prompt_semantics(wired, fields)
    violations = [*violations, *sem_violations]
    warnings = [
        *[f"unbound relative asset remains: {p}" for p in unbound_relative_assets(wired)],
        *sem_warnings,
    ]
    return {
        "ok": not violations,
        "simulate_parent": simulate_parent,
        "violations": violations,
        "warnings": warnings,
        "has_video_label": "<Video 1>" in wired,
        "wired": wired,
        "fields": fields,
    }


def preflight_job_dir(job_dir: Path, *, require_parent_path: bool = True) -> dict[str, object]:
    """Gate a built job: audit disk fields AND (by default) simulated parent path.

    Disk ``prompt_audit.json`` alone is insufficient for serial chains — U02+ only
    get ``ref_video_0`` at submit time.
    """
    import yaml

    job_dir = Path(job_dir)
    raw = yaml.safe_load((job_dir / "job.yaml").read_text(encoding="utf-8"))
    source = (job_dir / "assets" / "prompt_source.txt").read_text(encoding="utf-8")
    refs = {k: v for k, v in (raw.get("fields") or {}).items() if k.startswith("ref_")}
    reports = {
        "job_dir": str(job_dir),
        "unit_id": raw.get("unit_id"),
        "no_parent": preflight_pack_prompt(source, refs, simulate_parent=False),
    }
    if require_parent_path:
        reports["with_parent"] = preflight_pack_prompt(source, refs, simulate_parent=True)
    ok = bool(reports["no_parent"]["ok"]) and (
        (not require_parent_path) or bool(reports["with_parent"]["ok"])
    )
    reports["ok"] = ok
    # Drop bulky wired text from top-level consumers unless needed.
    for key in ("no_parent", "with_parent"):
        if key in reports and isinstance(reports[key], dict):
            reports[key] = {k: v for k, v in reports[key].items() if k != "wired"}
    return reports
