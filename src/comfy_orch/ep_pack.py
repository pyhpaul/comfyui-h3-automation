from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from comfy_orch.errors import ValidationError
from comfy_orch.h3_prompt import build_h3_r2v_prompt

TEMPLATE_NAME = "yz_h3_ep_unit"
IDENTITY_SLOT_COUNT = 5

_UPLOAD_ORDER_HEADER = re.compile(r"【本\s*U\s*实际上传顺序】")
_UPLOAD_ORDER_ITEM = re.compile(r"^\s*\d+\.\s+(\S+\.(?:png|jpe?g|webp|webm))\s*$", re.I)
_DURATION_PATTERNS = (
    re.compile(r"[｜|]\s*(\d+)\s*秒"),
    re.compile(r"[（(](\d+)\s*s[）)]", re.I),
    re.compile(r"duration_seconds\s*[:=]\s*(\d+)", re.I),
)
_EP_CODE = re.compile(r"^(EP\d+)", re.I)


def default_filename_prefix(episode: str, unit_id: str) -> str:
    """Comfy VHS filename_prefix: prefer EP##-U## when episode starts with EP."""
    m = _EP_CODE.match(episode.strip())
    if m:
        ep = m.group(1).upper()
    else:
        ep = re.sub(r"[^\w\-]+", "-", episode.strip(), flags=re.UNICODE)
        ep = re.sub(r"-{2,}", "-", ep).strip("-_") or "job"
    uid = unit_id.strip()
    if not uid.upper().startswith("U"):
        uid = f"U{uid}"
    return f"{ep}-{uid}"


@dataclass(frozen=True)
class UnitMediaPlan:
    unit_id: str
    control: str | None
    previz: str | None
    identities: list[str]
    prompt_rel: str
    duration_seconds: int
    pack_kind: str = "seedance_upload"


def parse_prompt_upload_order(text: str) -> list[str]:
    match = _UPLOAD_ORDER_HEADER.search(text)
    if not match:
        return []
    paths: list[str] = []
    for line in text[match.end() :].splitlines():
        if not line.strip():
            if paths:
                break
            continue
        if line.startswith("#") or line.startswith("##"):
            break
        item = _UPLOAD_ORDER_ITEM.match(line)
        if item:
            paths.append(item.group(1).replace("\\", "/"))
            continue
        if paths:
            break
    return paths


def parse_prompt_duration_seconds(text: str) -> int | None:
    for pattern in _DURATION_PATTERNS:
        found = pattern.search(text)
        if found:
            return int(found.group(1))
    return None


def map_yz_media_slots(
    *,
    control: str | None,
    previz: str | None,
    identities: list[str],
) -> dict[str, str]:
    """Map pack assets to YZ slots. No padding — only real files from the pack.

    Seedance: control→ref_image_0, identities→1..N, previz→ref_video_0.
    H3 latent (no control/previz): identities fill ref_image_0.. sequentially.
    """
    if not identities and not control:
        raise ValidationError("need at least one identity or control image")
    slots: dict[str, str] = {}
    if control:
        slots["ref_image_0"] = control
        start = 1
        id_cap = IDENTITY_SLOT_COUNT
    else:
        start = 0
        id_cap = IDENTITY_SLOT_COUNT + 1
    for offset, path in enumerate(identities[:id_cap]):
        idx = start + offset
        if idx > 5:
            break
        slots[f"ref_image_{idx}"] = path
    if previz:
        slots["ref_video_0"] = previz
    return slots


def _load_manifest(pack_root: Path) -> dict[str, Any]:
    path = pack_root / "upload-manifest.json"
    if not path.is_file():
        raise ValidationError(f"missing upload-manifest.json: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid upload-manifest.json: {path}") from exc
    if not isinstance(data, dict):
        raise ValidationError("upload-manifest.json must be an object")
    return data


def _find_unit(manifest: dict[str, Any], unit_id: str) -> dict[str, Any]:
    for unit in manifest.get("units") or []:
        if str(unit.get("unit_id")) == unit_id:
            return unit
    raise ValidationError(f"unit not found in manifest: {unit_id}")


def _path_field(obj: dict[str, Any] | None, *keys: str) -> str | None:
    cur: Any = obj
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    if isinstance(cur, str) and cur.strip():
        return cur.replace("\\", "/")
    return None


def _paths_from_upload_order(entries: Any) -> list[str]:
    out: list[str] = []
    if not isinstance(entries, list):
        return out
    for item in entries:
        if isinstance(item, str):
            out.append(item.replace("\\", "/"))
        elif isinstance(item, dict) and item.get("path"):
            out.append(str(item["path"]).replace("\\", "/"))
    return out


def _split_order(
    ordered: list[str],
    *,
    control: str,
    previz: str,
) -> list[str]:
    identities: list[str] = []
    for path in ordered:
        if path == control or path == previz:
            continue
        if path.endswith(".webm"):
            continue
        identities.append(path)
    return identities


def plan_unit(pack_root: Path, unit_id: str) -> UnitMediaPlan:
    pack_root = pack_root.resolve()
    unit = _find_unit(_load_manifest(pack_root), unit_id)

    prompt_rel = _path_field(unit, "prompt", "path") or f"prompts/{unit_id}.txt"
    prompt_path = pack_root / prompt_rel
    if not prompt_path.is_file():
        raise ValidationError(f"missing prompt: {prompt_rel}")
    prompt_text = prompt_path.read_text(encoding="utf-8")

    control = (
        _path_field(unit, "control_reference", "path")
        or _path_field(unit, "control", "path")
    )
    previz = (
        _path_field(unit, "previz_reference", "path")
        or _path_field(unit, "previz", "path")
    )
    ordered = _paths_from_upload_order(unit.get("upload_order"))
    if not ordered:
        ordered = parse_prompt_upload_order(prompt_text)

    if not control:
        control = next((p for p in ordered if "/control/" in f"/{p}" or p.startswith("control/")), None)
    if not previz:
        previz = next((p for p in ordered if p.endswith(".webm")), None)
    if not control or not previz:
        raise ValidationError(f"{unit_id}: need control and previz paths")

    identities = _split_order(ordered, control=control, previz=previz)
    duration = unit.get("duration_seconds")
    if duration is None:
        duration = parse_prompt_duration_seconds(prompt_text)
    if duration is None:
        duration = 10

    return UnitMediaPlan(
        unit_id=unit_id,
        control=control,
        previz=previz,
        identities=identities,
        prompt_rel=prompt_rel,
        duration_seconds=int(duration),
        pack_kind="seedance_upload",
    )


def _copy_into_job(src: Path, job_dir: Path, dest_name: str) -> str:
    if not src.is_file():
        raise ValidationError(f"missing pack file: {src}")
    dest_rel = Path("assets") / dest_name
    dest = job_dir / dest_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest_rel.as_posix()


def build_unit_job(pack_root: Path, unit_id: str, out_root: Path) -> Path:
    from comfy_orch.causality_pack import is_ep02_causality_pack, plan_causality_unit
    from comfy_orch.latent_pack import is_h3_latent_pack, plan_latent_unit

    pack_root = pack_root.resolve()
    if is_ep02_causality_pack(pack_root):
        plan = plan_causality_unit(pack_root, unit_id)
    elif is_h3_latent_pack(pack_root):
        plan = plan_latent_unit(pack_root, unit_id)
    else:
        plan = plan_unit(pack_root, unit_id)
    episode = pack_root.name
    job_dir = (out_root / f"{episode}-{plan.unit_id}").resolve()
    if job_dir.exists():
        shutil.rmtree(job_dir)
    job_dir.mkdir(parents=True)

    slots = map_yz_media_slots(
        control=plan.control,
        previz=plan.previz,
        identities=plan.identities,
    )
    field_paths: dict[str, str] = {}
    used_names: set[str] = set()

    def stage(pack_rel: str, role: str) -> str:
        src = pack_root / pack_rel
        base = Path(pack_rel).name
        name = f"{role}-{base}"
        if name in used_names:
            name = f"{role}-{Path(pack_rel).as_posix().replace('/', '__')}"
        used_names.add(name)
        return _copy_into_job(src, job_dir, name)

    for key, pack_rel in slots.items():
        if key == "ref_video_0":
            role = "previz"
        elif key == "ref_image_0" and plan.control:
            role = "control"
        else:
            role = key.replace("ref_image_", "id")
        field_paths[key] = stage(pack_rel, role)

    prompt_source = (pack_root / plan.prompt_rel).read_text(encoding="utf-8")
    if plan.pack_kind == "ep02_causality":
        from comfy_orch.errors import ValidationError
        from comfy_orch.prompt_wire import audit_pack_prompt_wiring, wire_pack_prompt

        prompt_wired = wire_pack_prompt(prompt_source, field_paths)
        violations = audit_pack_prompt_wiring(prompt_source, prompt_wired, field_paths)
        if violations:
            raise ValidationError("prompt wiring audit failed: " + "; ".join(violations))
        prompt_h3 = prompt_wired
    elif plan.pack_kind == "h3_latent":
        from comfy_orch.h3_prompt import build_h3_r2v_prompt_latent

        prompt_h3 = build_h3_r2v_prompt_latent(prompt_source, field_paths)
    else:
        prompt_h3 = build_h3_r2v_prompt(prompt_source, field_paths)

    assets_dir = job_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "prompt_source.txt").write_text(prompt_source, encoding="utf-8")
    (assets_dir / "prompt_h3.txt").write_text(prompt_h3, encoding="utf-8")
    (assets_dir / "prompt.txt").write_text(prompt_h3, encoding="utf-8")
    if plan.pack_kind == "ep02_causality":
        (assets_dir / "prompt_audit.json").write_text(
            __import__("json").dumps(
                {"ok": True, "mode": "wire_media_labels_only", "violations": []},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    payload = {
        "template": TEMPLATE_NAME,
        "episode": episode,
        "unit_id": plan.unit_id,
        "pack_kind": plan.pack_kind,
        "fields": {
            **field_paths,
            "prompt": prompt_h3,
            "duration_seconds": plan.duration_seconds,
            "aspect_ratio": "9:16 (Portrait Widescreen)",
            "megapixels": 1.0,
            "filename_prefix": default_filename_prefix(episode, plan.unit_id),
        },
    }
    (job_dir / "job.yaml").write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return job_dir


def list_unit_ids(pack_root: Path) -> list[str]:
    from comfy_orch.causality_pack import is_ep02_causality_pack, list_causality_unit_ids
    from comfy_orch.latent_pack import is_h3_latent_pack, list_latent_unit_ids

    pack_root = pack_root.resolve()
    if is_ep02_causality_pack(pack_root):
        return list_causality_unit_ids(pack_root)
    if is_h3_latent_pack(pack_root):
        return list_latent_unit_ids(pack_root)
    units = _load_manifest(pack_root).get("units") or []
    return [str(u["unit_id"]) for u in units if u.get("unit_id")]


def build_pack_jobs(
    pack_root: Path,
    out_root: Path,
    *,
    unit_ids: list[str] | None = None,
) -> list[Path]:
    ids = unit_ids or list_unit_ids(pack_root)
    return [build_unit_job(pack_root, uid, out_root) for uid in ids]
