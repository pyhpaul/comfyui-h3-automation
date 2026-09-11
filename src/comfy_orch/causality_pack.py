from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from comfy_orch.ep_pack import UnitMediaPlan
from comfy_orch.errors import ValidationError

_DURATION = re.compile(r"目标时长[：:]\s*(\d+(?:\.\d+)?)\s*秒")
_SHOT = re.compile(
    r"【镜头\s*(\d+)\s*｜\s*([^｜]+)｜\s*([^】]+)】\s*(.+?)(?=\n【镜头|\n【交出|\n【H3|\n【测试|\Z)",
    re.S,
)
_DIALOGUE = re.compile(r'[“"]([^”"]+)[”"]')
_ASSET_PATH = re.compile(
    r"assets[/\\](?:characters|props|scenes)[/\\][^\s]+\.(?:png|jpe?g|webp)",
    re.I,
)


def is_ep02_causality_pack(pack_root: Path) -> bool:
    root = pack_root.resolve()
    return (
        (root / "manifest.json").is_file()
        and (root / "assets").is_dir()
        and (root / "ep02" / "prompts").is_dir()
        and not (root / "upload-manifest.json").is_file()
    )


def _load_manifest(pack_root: Path) -> dict[str, Any]:
    path = pack_root / "manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid manifest.json: {path}") from exc
    if not isinstance(data, dict):
        raise ValidationError("manifest.json must be an object")
    return data


def list_causality_unit_ids(pack_root: Path) -> list[str]:
    units = _load_manifest(pack_root.resolve()).get("units") or []
    out: list[str] = []
    for u in units:
        uid = str(u.get("unit") or u.get("unit_id") or "")
        if not uid:
            continue
        m = re.match(r"U?(\d+)$", uid, re.I)
        out.append(f"U{int(m.group(1)):02d}" if m else uid)
    return out


def _norm_unit(unit_id: str) -> str:
    want = unit_id.upper()
    if not want.startswith("U"):
        want = f"U{want}"
    m = re.match(r"U(\d+)$", want, re.I)
    return f"U{int(m.group(1)):02d}" if m else want


def _find_unit(manifest: dict[str, Any], unit_id: str) -> dict[str, Any]:
    want = _norm_unit(unit_id)
    for unit in manifest.get("units") or []:
        uid = str(unit.get("unit") or unit.get("unit_id") or "")
        if _norm_unit(uid) == want:
            return unit
    raise ValidationError(f"unit not found in causality manifest: {unit_id}")


def _to_pack_rel(path: str) -> str:
    text = path.replace("\\", "/")
    idx = text.lower().find("/assets/")
    if idx >= 0:
        return text[idx + 1 :]
    if text.startswith("assets/"):
        return text
    return text.lstrip("/")


def parse_causality_sections(text: str) -> dict[str, str]:
    def section(name: str) -> str:
        m = re.search(rf"【{re.escape(name)}】\s*(.+?)(?=\n【|\Z)", text, re.S)
        return m.group(1).strip() if m else ""

    dur_m = _DURATION.search(text)
    title_m = re.search(r"｜\s*(U\d+)\s*｜\s*(.+)", text)
    return {
        "unit_id": title_m.group(1) if title_m else "",
        "title": title_m.group(2).strip() if title_m else "unit",
        "duration_seconds": str(int(float(dur_m.group(1)))) if dur_m else "10",
        "effect": section("本U画面效果与完整流程"),
        "latent_in": section("H3 latent 接入文字"),
        "constraints": section("画面总约束"),
        "handoff": section("交出状态"),
        "latent_relay": section("H3 latent 接力文字"),
        "body": text,
    }


def parse_causality_shots(text: str) -> list[tuple[int, str, str, str]]:
    shots: list[tuple[int, str, str, str]] = []
    for m in _SHOT.finditer(text):
        shots.append(
            (
                int(m.group(1)),
                m.group(2).strip(),
                m.group(3).strip(),
                m.group(4).strip(),
            )
        )
    return shots


def parse_causality_dialogues(text: str) -> list[str]:
    """Keep only English spoken lines (skip Chinese narrative quotes)."""
    lines: list[str] = []
    for m in re.finditer(r'[“"\']([^”"\']+)[”"\']', text):
        line = m.group(1).strip()
        if not re.search(r"[A-Za-z]", line):
            continue
        # Reject mixed CJK narrative snippets.
        if re.search(r"[\u4e00-\u9fff]", line):
            continue
        if line not in lines:
            lines.append(line)
    return lines


def plan_causality_unit(pack_root: Path, unit_id: str) -> UnitMediaPlan:
    pack_root = pack_root.resolve()
    manifest = _load_manifest(pack_root)
    unit = _find_unit(manifest, unit_id)
    uid = _norm_unit(str(unit.get("unit") or unit_id))

    prompt_field = str(unit.get("prompt") or f"ep02/prompts/{uid}.txt").replace("\\", "/")
    prompt_rel = prompt_field
    if not (pack_root / prompt_rel).is_file():
        alt = f"ep02/prompts/{uid}.txt"
        if (pack_root / alt).is_file():
            prompt_rel = alt
        else:
            raise ValidationError(f"{uid}: missing prompt {prompt_field}")

    identities: list[str] = []
    for raw in unit.get("upload_assets") or []:
        rel = _to_pack_rel(str(raw))
        src = pack_root / rel
        if not src.is_file():
            name = Path(rel).name
            found = list(pack_root.glob(f"assets/**/{name}"))
            if not found:
                raise ValidationError(f"{uid}: missing asset {rel}")
            rel = found[0].relative_to(pack_root).as_posix()
        identities.append(Path(rel).as_posix())

    if not identities:
        raise ValidationError(f"{uid}: no upload_assets in manifest")

    # YZ template wires at most ref_image_0..5 (6 stills). Prefer scene + stamp.
    if len(identities) > 6:
        scenes = [p for p in identities if "/scenes/" in p]
        stamps = [p for p in identities if "stamp" in Path(p).name.lower()]
        rest = [p for p in identities if p not in scenes and p not in stamps]
        trimmed = rest[: max(0, 6 - len(scenes[-1:]) - len(stamps[-1:]))]
        identities = trimmed + stamps[-1:] + scenes[-1:]
        identities = identities[:6]

    duration = int(unit.get("duration_seconds") or 0)
    if duration <= 0:
        text = (pack_root / prompt_rel).read_text(encoding="utf-8")
        duration = int(parse_causality_sections(text)["duration_seconds"])

    return UnitMediaPlan(
        unit_id=uid,
        control=None,
        previz=None,
        identities=identities,
        prompt_rel=prompt_rel,
        duration_seconds=duration,
        pack_kind="ep02_causality",
    )
