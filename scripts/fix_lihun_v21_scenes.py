#!/usr/bin/env python3
"""Crop 离婚后 EP four-grid scenes to the locked camera panel + bracket spacing.

Usage: fix_lihun_v21_scenes.py EP01 [EP02 ...]
Panels are locked per (episode, scene) in PANEL_MAP below, matched
against the pack's own observer_side/space_axis and the panel landmarks.
Only episodes whose panels have been verified may be added. Also
normalises Latin-only dialogue brackets to （ text ）. Body text is
otherwise untouched. Full four-grids are backed up under job/scene_full/.
Does not queue.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comfy_orch.prompt_wire import preflight_job_dir, wire_pack_prompt  # noqa: E402

PANELS = {  # 1672x941, thin cross at x~836 / y~470 (chaofu coords verified visually)
    "TL": (0, 0, 833, 468),
    "TR": (839, 0, 833, 468),
    "BL": (0, 474, 833, 467),
    "BR": (839, 474, 833, 467),
}

# (episode, scene asset id) -> (panel, single-panel description)
PANEL_MAP = {
    ("EP01", "scene-001-s01"): (
        "TR",
        "参考图是西侧朝东的单幅：北侧落地窗和沙发在画面左，"
        "南侧餐边柜和油画在画面右，东墙双开门在画面深处。",
    ),
    # EP02-U01/U06 餐厅白天版，机位北侧朝南（与 S01 同布局：BL=北→南）
    ("EP02", "scene-001-s02"): (
        "BL",
        "参考图是北侧朝南的单幅：南墙餐边柜和油画在前方，"
        "东墙双开门在画面左，西墙楼梯在画面右。",
    ),
    # EP03 全集旅馆房间，机位西侧朝东（TR=西→东）
    ("EP03", "scene-003-s01"): (
        "TR",
        "参考图是西侧朝东的单幅：北侧双人床在画面左，"
        "东墙窗帘在画面中，南墙房门在画面右。",
    ),
    # EP02-U02..U05 卧室，机位东侧/东北侧朝西（BR=东→西）
    ("EP02", "scene-002-s01"): (
        "BR",
        "参考图是东侧朝西的单幅：西墙衣柜在画面正中，"
        "北侧大床在画面右，南墙房门在画面左。",
    ),
    # EP04 全集客厅，机位东侧朝西（BR=东→西；四格已逐格核：
    # TL=南→北、TR=西→东、BL=北→南、BR=东→西）
    ("EP04", "scene-004-s01"): (
        "BR",
        "参考图是东侧朝西的单幅：西墙双开门在画面深处，"
        "南墙落地窗在画面左，中央长沙发在画面右，西北角用餐区在画面右后。",
    ),
    # EP05 全集同一客厅，机位南侧朝北（TL=南→北）
    ("EP05", "scene-004-s01"): (
        "TL",
        "参考图是南侧朝北的单幅：北墙边柜和抽象画在画面深处，"
        "东墙壁炉在画面右，西墙双开门在画面左，中央长沙发正面朝南在画面中。",
    ),
    # EP06 全集同一客厅，机位东侧朝西（BR=东→西，同 EP04）
    ("EP06", "scene-004-s01"): (
        "BR",
        "参考图是东侧朝西的单幅：西墙双开门在画面深处，"
        "南墙落地窗在画面左，中央长沙发在画面右，西北角用餐区在画面右后。",
    ),
}

_LATIN_BRACKET = re.compile(r"（([A-Za-z0-9][^（）]*?)）")


def space_dialogue(text: str) -> str:
    def repl(m: re.Match) -> str:
        inner = m.group(1)
        if not re.search(r"[A-Za-z]", inner) or re.search(r"[\u4e00-\u9fff]", inner):
            return m.group(0)
        return f"（ {inner.strip()} ）"

    return _LATIN_BRACKET.sub(repl, text)


def crop_panel(src: Path, panel: str, dest: Path) -> None:
    x, y, w, h = PANELS[panel]
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(src), "-vf",
         f"crop={w}:{h}:{x}:{y}", "-frames:v", "1", "-y", str(dest)],
        check=True)


def main() -> int:
    episodes = [a.upper() for a in sys.argv[1:]]
    if not episodes:
        raise SystemExit("usage: fix_lihun_v21_scenes.py EP01 [EP02 ...]")
    for ep in episodes:
        jobs = sorted((ROOT / "jobs" / "ep_units").glob(f"{ep}-继母-v21-U*"))
        if not jobs:
            raise SystemExit(f"no jobs for {ep}")
        for job in jobs:
            assets = job / "assets"
            raw = yaml.safe_load((job / "job.yaml").read_text(encoding="utf-8"))
            fields = raw["fields"]
            crops = []
            for key, rel in fields.items():
                if not key.startswith("ref_image_"):
                    continue
                name = Path(str(rel)).name
                if "-scene-" not in name:
                    continue
                aid = name.split("-", 1)[1].rsplit(".", 1)[0]
                if (ep, aid) not in PANEL_MAP:
                    raise SystemExit(
                        f"{job.name}: no locked panel for {aid}; "
                        "verify quadrants before adding to PANEL_MAP")
                panel, desc = PANEL_MAP[(ep, aid)]
                img = job / str(rel)
                backup_dir = job / "scene_full"
                backup_dir.mkdir(exist_ok=True)
                backup = backup_dir / f"{aid}.png"
                if not backup.exists():
                    backup.write_bytes(img.read_bytes())
                crop_panel(backup, panel, img)
                crops.append((aid, panel))
            source = (assets / "prompt_source.txt").read_text(encoding="utf-8")
            source = space_dialogue(source)
            lines = source.splitlines()
            changed = 0
            for i, line in enumerate(lines):
                if "@scene-" not in line or "四格" not in line:
                    continue
                aid = re.search(r"@(scene-\d+-s\d+)", line, re.I).group(1).lower()
                panel, desc = PANEL_MAP[(ep, aid)]
                if "四格参考只用于锁定空间方位，视频画面不出现四格拼版。" in line:
                    lines[i] = line.replace(
                        "四格参考只用于锁定空间方位，视频画面不出现四格拼版。", desc)
                else:
                    lines[i] = line.replace(
                        "视频画面不出现四格拼版。", desc + "视频画面不出现拼版。")
                changed += 1
            expected = sum(1 for l in source.splitlines() if "@scene-" in l and "四格" in l)
            if changed != expected:
                raise SystemExit(f"{job.name}: scene lines {changed}/{expected}")
            new_source = "\n".join(lines).rstrip() + "\n"
            (assets / "prompt_source.txt").write_text(new_source, encoding="utf-8")
            refs = {k: v for k, v in fields.items() if k.startswith("ref_image_")}
            wired = wire_pack_prompt(new_source, refs)
            fields["prompt"] = wired
            (job / "job.yaml").write_text(
                yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
            (assets / "prompt_h3.txt").write_text(wired, encoding="utf-8")
            pf = preflight_job_dir(job, require_parent_path=True)
            print(f"{job.name} crops={crops} preflight_ok={pf['ok']}", flush=True)
            if not pf["ok"]:
                print(pf)
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
