from __future__ import annotations

import re
from pathlib import Path

_WIN_OR_REL_ASSET = re.compile(
    r"(?:[A-Za-z]:[\\/][^\n]*?[\\/])?(?:assets|images)[\\/](?:characters|props|scenes)[\\/]([^\s\\/]+?\.(?:png|jpe?g|webp))",
    re.I,
)
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

    # Any leftover Windows absolute asset paths → pack-relative assets/...
    # (for listed assets not bound to a Picture slot, e.g. U07 7th still)
    def _rel_only(m: re.Match[str]) -> str:
        return f"assets/{m.group(0).replace(chr(92), '/').split('/assets/')[-1]}"

    out = re.sub(
        r"[A-Za-z]:[\\/][^\n]*?[\\/](assets[\\/](?:characters|props|scenes)[\\/][^\s\\/]+?\.(?:png|jpe?g|webp))",
        lambda m: m.group(1).replace("\\", "/"),
        out,
        flags=re.I,
    )

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
    text = _WIN_OR_REL_ASSET.sub("", text)
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
    wired = wire_pack_prompt(source, fields)
    violations = audit_pack_prompt_wiring(source, wired, fields)
    warnings = [f"unbound relative asset remains: {p}" for p in unbound_relative_assets(wired)]
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
