from __future__ import annotations

import re
from pathlib import Path

from comfy_orch.ep_pack import UnitMediaPlan, parse_prompt_duration_seconds
from comfy_orch.errors import ValidationError

_UNIT_FILE = re.compile(r"^(U\d+)_.+\.txt$", re.I)
_ASSET_LINE = re.compile(
    r"^\s*\d+\.\s+(.+?(?:images[/\\](?:characters|props|scenes)[/\\][^\s]+\.(?:png|jpe?g|webp)))\s*$",
    re.I,
)
_TITLE = re.compile(
    r"^EP\d+\s+(U\d+)\s*[｜|]\s*(.+?)\s*[｜|]\s*(\d+)\s*秒",
    re.I | re.M,
)


def is_h3_latent_pack(pack_root: Path) -> bool:
    root = pack_root.resolve()
    return (
        (root / "images").is_dir()
        and (root / "prompts").is_dir()
        and not (root / "upload-manifest.json").is_file()
    )


def list_latent_unit_ids(pack_root: Path) -> list[str]:
    prompts = pack_root.resolve() / "prompts"
    ids: list[str] = []
    for path in sorted(prompts.glob("U*.txt")):
        m = _UNIT_FILE.match(path.name)
        if not m:
            continue
        num = re.match(r"U(\d+)", m.group(1), re.I)
        ids.append(f"U{int(num.group(1)):02d}" if num else m.group(1))
    return ids


def find_latent_prompt_rel(pack_root: Path, unit_id: str) -> str:
    prompts = pack_root / "prompts"
    want = unit_id.upper()
    if not want.startswith("U"):
        want = f"U{want}"
    # U1 → U01
    m = re.match(r"U(\d+)$", want, re.I)
    if m:
        want = f"U{int(m.group(1)):02d}"
    for path in sorted(prompts.glob("U*.txt")):
        fm = _UNIT_FILE.match(path.name)
        if not fm:
            continue
        num = re.match(r"U(\d+)", fm.group(1), re.I)
        uid = f"U{int(num.group(1)):02d}" if num else fm.group(1)
        if uid.upper() == want.upper():
            return f"prompts/{path.name}"
    raise ValidationError(f"latent prompt not found for {unit_id}")


def _to_pack_rel(abs_or_rel: str) -> str:
    text = abs_or_rel.replace("\\", "/")
    idx = text.lower().find("/images/")
    if idx >= 0:
        return text[idx + 1 :]  # images/...
    if text.startswith("images/"):
        return text
    # bare filename search left to caller
    return text.lstrip("/")


def parse_latent_asset_paths(text: str) -> list[str]:
    paths: list[str] = []
    in_block = False
    for line in text.splitlines():
        if "资产上传路径" in line:
            in_block = True
            continue
        if in_block:
            if not line.strip():
                if paths:
                    break
                continue
            if line.startswith("全局") or line.startswith("提示词") or line.startswith("latent"):
                break
            m = _ASSET_LINE.match(line)
            if m:
                paths.append(_to_pack_rel(m.group(1)))
                continue
            if paths:
                break
    return paths


def parse_latent_sections(text: str) -> dict[str, str]:
    title_m = _TITLE.search(text)
    style = ""
    latent = ""
    body = ""
    m_style = re.search(r"全局画风[：:]\s*(.+?)(?=\n\s*\n|latent|提示词)", text, re.S)
    if m_style:
        style = " ".join(m_style.group(1).split())
    m_lat = re.search(r"latent\s*接力文字[：:]\s*(.+?)(?=\n提示词|\Z)", text, re.S | re.I)
    if m_lat:
        latent = " ".join(m_lat.group(1).split())
    m_body = re.search(r"提示词[：:]\s*(.+)\Z", text, re.S)
    if m_body:
        body = " ".join(m_body.group(1).split())
    duration = None
    if title_m:
        duration = int(title_m.group(3))
    if duration is None:
        duration = parse_prompt_duration_seconds(text)
    return {
        "unit_id": title_m.group(1) if title_m else "",
        "title": title_m.group(2).strip() if title_m else "unit",
        "duration_seconds": str(duration or 10),
        "style": style,
        "latent": latent,
        "body": body,
    }


def plan_latent_unit(pack_root: Path, unit_id: str) -> UnitMediaPlan:
    pack_root = pack_root.resolve()
    prompt_rel = find_latent_prompt_rel(pack_root, unit_id)
    prompt_text = (pack_root / prompt_rel).read_text(encoding="utf-8")
    rels = parse_latent_asset_paths(prompt_text)
    if not rels:
        raise ValidationError(f"{unit_id}: no asset paths in latent prompt")
    identities: list[str] = []
    for rel in rels:
        src = pack_root / rel
        if not src.is_file():
            # try basename under images/
            name = Path(rel).name
            found = list(pack_root.glob(f"images/**/{name}"))
            if not found:
                raise ValidationError(f"{unit_id}: missing image {rel}")
            rel = found[0].relative_to(pack_root).as_posix()
        identities.append(rel)
    sections = parse_latent_sections(prompt_text)
    return UnitMediaPlan(
        unit_id=unit_id if unit_id.startswith("U") else sections["unit_id"] or unit_id,
        control=None,
        previz=None,
        identities=identities,
        prompt_rel=prompt_rel,
        duration_seconds=int(sections["duration_seconds"]),
        pack_kind="h3_latent",
    )
