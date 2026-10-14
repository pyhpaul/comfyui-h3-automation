"""Motion-latent chain must stay inside one scene location.

Scene plates that share a number are one place at different times of day
(``scene-004-s01`` night and ``scene-004-s03`` day). A different number is a
different place. Parenting the previous unit's motion latent across that cut
replays the old place at the tail of every later unit.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_SCENE_IN_REF = re.compile(r"scene-(\d+)", re.I)
_UNIT_NUM = re.compile(r"^U(\d+)", re.I)


def scene_families_from_fields(fields: dict) -> set[int]:
    """Location numbers bound as reference images. Prompt text does not count."""
    families: set[int] = set()
    for key, value in fields.items():
        if not str(key).startswith("ref_image_"):
            continue
        for match in _SCENE_IN_REF.finditer(str(value)):
            families.add(int(match.group(1)))
    return families


def _unit_number(unit_id: str) -> int | None:
    match = _UNIT_NUM.match(unit_id.strip())
    if not match:
        return None
    return int(match.group(1))


def _label(families: set[int]) -> str:
    return "+".join(f"scene-{n:03d}" for n in sorted(families))


def breaks_motion_chain(start_mode: str | None) -> bool:
    """An independent unit loads no parent latent and no parent video."""
    return (start_mode or "") == "independent"


def audit_latent_scene_chain(
    units: list[tuple[str, str, set[int]] | tuple[str, str, set[int], str]],
) -> list[str]:
    """Flag consecutive units whose bound scenes do not overlap.

    ``units`` items are ``(episode, unit_id, scene_families)`` or the same
    tuple plus ``start_mode``. Only pairs whose unit numbers differ by 1 are
    checked, matching a serial motion-latent run. A unit with no scene image
    is skipped. ``start_mode=independent`` already loads no parent, so that
    pair is not a violation.
    """
    grouped: dict[str, list[tuple[int, str, set[int], str]]] = {}
    for item in units:
        episode, unit_id, families = item[0], item[1], item[2]
        number = _unit_number(unit_id)
        if number is None:
            continue
        start_mode = item[3] if len(item) > 3 else ""
        grouped.setdefault(episode, []).append((number, unit_id, families, start_mode))

    violations: list[str] = []
    for episode, rows in grouped.items():
        rows.sort(key=lambda row: row[0])
        for prev, nxt in zip(rows, rows[1:]):
            if nxt[0] != prev[0] + 1:
                continue
            if breaks_motion_chain(nxt[3]):
                continue
            if not prev[2] or not nxt[2] or prev[2] & nxt[2]:
                continue
            violations.append(
                f"{episode} {nxt[1]} 场景 {_label(nxt[2])} 与上一条 {prev[1]} "
                f"场景 {_label(prev[2])} 不同，motion latent 必须断开"
            )
    return violations


def audit_job_dirs(job_dirs: list[Path]) -> list[str]:
    units: list[tuple[str, str, set[int]]] = []
    for job_dir in job_dirs:
        raw = yaml.safe_load((Path(job_dir) / "job.yaml").read_text(encoding="utf-8")) or {}
        fields = raw.get("fields") or {}
        episode = str(raw.get("episode") or Path(job_dir).name)
        unit_id = str(raw.get("unit_id") or "")
        units.append(
            (
                episode,
                unit_id,
                scene_families_from_fields(fields),
                str(raw.get("start_mode") or ""),
            )
        )
    return audit_latent_scene_chain(units)
