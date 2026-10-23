#!/usr/bin/env python3
"""Crop 潮缚 EP01-EP06 fx21 (审核修正版) scene four-grids to the locked camera panel.

Panels were matched against the pack's own N/E/S/W landmark lines and
verified pixel-wise against the v1 crops of the identical four-grids:
scene-001 BR = east looking west, scene-002 TL = south looking north,
scene-003 TL = south-end looking north, scene-004 TL = south looking
north, scene-005 BL = north looking south. EP03-U07's deck flashback
looks south from north of the rope, so its aux scene-001 takes BL.

Also normalises Latin-only dialogue brackets to （ text ）. Body text is
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

PANELS = {  # 1672x941, white cross at x 833-838 / y 468-473
    "TL": (0, 0, 833, 468),
    "TR": (839, 0, 833, 468),
    "BL": (0, 474, 833, 467),
    "BR": (839, 474, 833, 467),
}

DESC = {
    ("scene-001-s01", "BR"): "参考图是东侧朝西的单幅：北侧驾驶舱和声呐在画面右，西侧海面在前方。",
    ("scene-001-s01", "BL"): "参考图是北侧朝南的单幅：船尾横栏和栏杆门在前方，南侧海面在栏杆外。",
    ("scene-002-s01", "TL"): "参考图是南侧朝北的单幅：舱口在画面中，船首在前方北端，东侧淤泥台在画面右。",
    ("scene-003-s01", "TL"): "参考图是南端朝北的单幅：西侧仓库在画面左，东侧泊位在画面右，北侧海面在前方。",
    ("scene-004-s01", "TL"): "参考图是南侧朝北的单幅：入户门在画面左近处，北墙海窗在前方，东墙餐边柜在画面右。",
    ("scene-005-s01", "BL"): "参考图是北侧朝南的单幅：南墙入户门在前方，西墙水槽台面在画面右，东墙灶台在画面左。",
    ("scene-006-s01", "BR"): "参考图是东南侧朝西北的单幅：深蓝色大门和门东侧壁灯在画面右，门廊木台阶在画面右下，南面海面和港口灯火在画面左。",
}

_LATIN_BRACKET = re.compile(r"（([A-Za-z0-9][^（）]*?)）")


def panel_for(job_name: str, aid: str) -> str:
    if aid == "scene-001-s01" and job_name == "EP03-潮缚-fx21-U07":
        return "BL"
    return {
        "scene-001-s01": "BR",
        "scene-002-s01": "TL",
        "scene-003-s01": "TL",
        "scene-004-s01": "TL",
        "scene-005-s01": "BL",
        "scene-006-s01": "BR",
    }[aid]


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
    jobs = sorted((ROOT / "jobs" / "ep_units").glob("EP0[1-6]-潮缚-fx21-U*"))
    if len(jobs) != 39:
        raise SystemExit(f"expected 39 fx21 jobs, got {len(jobs)}")
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
            panel = panel_for(job.name, aid)
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
            # a job can bind the same scene once; aux lines share the aid
            panels = [p for a, p in crops if a == aid]
            if line.startswith("辅助场景") and aid == "scene-001-s01" \
                    and job.name == "EP03-潮缚-fx21-U07":
                panel = "BL"
            elif line.startswith("辅助场景") and aid == "scene-002-s01":
                panel = "TL"
            elif line.startswith("辅助场景") and aid == "scene-005-s01":
                panel = "BL"
            else:
                panel = panels[0]
            desc = DESC[(aid, panel)]
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
        audit_path = assets / "prompt_audit.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        audit["scene_crops"] = [{"asset_id": a, "panel": p} for a, p in crops]
        audit_path.write_text(
            json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
        pf = preflight_job_dir(job, require_parent_path=True)
        print(f"{job.name} crops={crops} preflight_ok={pf['ok']}", flush=True)
        if not pf["ok"]:
            print(pf)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
