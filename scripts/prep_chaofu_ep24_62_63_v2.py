"""Prep for the EP24 whole-episode redo (v2 jobs already unpacked).

Diagnosis (2026-10-21): EP23-U04's shipped film uses the porch's along-deck
axis with the wall/door on the LEFT (the four-grid's top-right panel).
Earlier EP24 renders used the mirrored bottom-right panel (fix rounds) or
the door-front panel, so the geography never matched EP23. fix2 only added
night/exposure locks and never cropped the grid.

This script, for EP24 U01-U05:
  - crops the porch four-grid to its TOP-RIGHT panel (same axis as the
    EP23-U04 film) and replaces the scene ref inside assets/ (the full
    grid is backed up outside assets/, where the runner never uploads);
  - replaces the "四格参考..." sentence with a single-panel layout note;
  - appends the proven fix1 night lock + fix2 exposure lock;
  - applies fix1's dialogue locks (repeat lock, per-shot only-speaker,
    lips-lock) by importing make_chaofu_fix1_jobs.
For EP24 U06 (kitchen, no dialogue):
  - crops the kitchen four-grid to its top-right panel (south door on the
    right, north window on the left -- matches Cole backing the south
    door, cameras north of the round table) and swaps the grid sentence.
EP62/EP63: no crops and no scene-sentence edits (multi-direction units,
no shipped-film benchmark -- cropping any single panel would starve the
other directions; the four-grid stays, as unpacked). They DO get fix1's
dialogue locks, which only append and never rewrite body text.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
JOBS = ROOT / "jobs" / "ep_units"

# four-grid 1672x941, white cross at (836, 470); inset to dodge the seam
TR_BOX = (844, 8, 1664, 462)

PORCH_LAYOUT = (
    "本场景参考图为单幅画面：画面左侧是北侧木墙、入户门与门廊灯，"
    "木板地向右延伸至白色栏杆与夜色中的海面。视频画面不出现四格拼版。"
)
KITCHEN_LAYOUT = (
    "本场景参考图为单幅画面：圆木桌位于画面中央，北墙窗户在画面左侧，"
    "南墙入户门在画面右侧。视频画面不出现四格拼版。"
)
GRID_SENTENCE = "四格参考只用于锁定空间方位，视频画面不出现四格拼版。"

EXPOSURE_LOCK = (
    "整体画面曝光明显压暗，阴影暗部接近纯黑；"
    "天空与海面不允许出现蓝色、灰色或任何天光亮度，"
    "画面中唯一可见的光源就是门廊灯的暖光。"
)


def load_fix1():
    spec = importlib.util.spec_from_file_location(
        "fix1", ROOT / "scripts" / "make_chaofu_fix1_jobs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def crop_tr(src: Path, dst: Path) -> None:
    with Image.open(src) as im:
        assert im.size == (1672, 941), (src, im.size)
        im.crop(TR_BOX).save(dst)


def patch_job(unit_dir: Path, scene_glob: str, layout: str,
              fix1, dialogue: bool, night: bool) -> list[str]:
    edits: list[str] = []
    assets = unit_dir / "assets"
    scene_files = sorted(assets.glob(scene_glob))
    assert len(scene_files) == 1, (unit_dir, scene_files)
    scene = scene_files[0]

    backup_dir = unit_dir / "scene_grid_full"
    backup_dir.mkdir(exist_ok=True)
    backup = backup_dir / scene.name
    if not backup.exists():
        backup.write_bytes(scene.read_bytes())
        crop_tr(backup, scene)
        edits.append(f"crop TR -> {scene.name} (grid backed up)")
    else:
        edits.append("scene already cropped")

    p = assets / "prompt_source.txt"
    text = p.read_text(encoding="utf-8")
    if GRID_SENTENCE in text:
        text = text.replace(GRID_SENTENCE, layout, 1)
        edits.append("grid-sentence -> single-panel layout")
    if dialogue:
        text = fix1.patch_dialogue(text, unit_dir.name, edits)
    if night:
        text = fix1.patch_ep24_night(text, edits)
        if EXPOSURE_LOCK not in text:
            import re
            m = re.search(r"(【氛围与画质】[^\n]*)", text)
            assert m, unit_dir
            text = text.replace(
                m.group(1), m.group(1).rstrip() + EXPOSURE_LOCK, 1)
            edits.append("exposure-lock")
    p.write_text(text, encoding="utf-8")
    (assets / "prompt_audit.json").unlink(missing_ok=True)
    return edits


def main() -> int:
    fix1 = load_fix1()
    for i in range(1, 6):
        d = JOBS / f"EP24-潮缚-v2-U0{i}"
        edits = patch_job(d, "*scene-011-s02*", PORCH_LAYOUT, fix1,
                          dialogue=True, night=True)
        print(f"EP24-U0{i}: {'; '.join(edits)}")
    d = JOBS / "EP24-潮缚-v2-U06"
    edits = patch_job(d, "*scene-005-s02*", KITCHEN_LAYOUT, fix1,
                      dialogue=False, night=False)
    print(f"EP24-U06: {'; '.join(edits)}")
    for ep, count in (("EP62", 7), ("EP63", 6)):
        for i in range(1, count + 1):
            d = JOBS / f"{ep}-潮缚-v2-U0{i}"
            p = d / "assets" / "prompt_source.txt"
            text = p.read_text(encoding="utf-8")
            edits = []
            text = fix1.patch_dialogue(text, d.name, edits)
            p.write_text(text, encoding="utf-8")
            (d / "assets" / "prompt_audit.json").unlink(missing_ok=True)
            print(f"{ep}-U0{i}: {'; '.join(edits) if edits else 'no edits'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
