#!/usr/bin/env python3
"""Crop 寿命掮客 EP01-EP06 v1 scene four-grids to the locked camera panel.

Panels use the grids' own burned-in labels (TL=FACING NORTH, TR=FACING
EAST, BL=FACING SOUTH, BR=FACING WEST), verified against each pack scene
line's N/E/S/W landmarks. Panel choice is per unit from its
摄影机观察侧 / shooting direction (dominant direction; reverse close-ups
stay on the dominant panel, as in the chaofu/lihun fixes).

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

PANELS = {  # 1672x941, white cross at x ~836-839 / y ~468-472
    "TL": (0, 0, 833, 468),
    "TR": (839, 0, 833, 468),
    "BL": (0, 474, 833, 467),
    "BR": (839, 474, 833, 467),
}

# (job suffix EPxx-Uxx) -> panel. Default TL (south-side camera looking north).
PANEL_BY_UNIT = {}
for _u in range(1, 10):
    PANEL_BY_UNIT[f"EP01-U{_u:02d}"] = "TL"
    PANEL_BY_UNIT[f"EP05-U{_u:02d}"] = "TL"
for _u in range(1, 6):
    PANEL_BY_UNIT[f"EP02-U{_u:02d}"] = "TL"
for _u in range(6, 10):
    PANEL_BY_UNIT[f"EP02-U{_u:02d}"] = "BL"  # NE side, counter/clock (south) behind subjects
for _u in range(1, 6):
    PANEL_BY_UNIT[f"EP03-U{_u:02d}"] = "BL"
PANEL_BY_UNIT["EP03-U06"] = "TR"  # axis Kai->revolving door (east), door is destination
PANEL_BY_UNIT["EP03-U07"] = "TL"
PANEL_BY_UNIT["EP03-U08"] = "TL"
for _u in range(1, 11):
    PANEL_BY_UNIT[f"EP04-U{_u:02d}"] = "TL"
PANEL_BY_UNIT["EP06-U01"] = "TL"  # south cabinet looking north to screen/main seat
for _u in range(2, 10):
    PANEL_BY_UNIT[f"EP06-U{_u:02d}"] = "TR"  # west side looking east to glass wall

DESC = {
    ("scene-001-s01", "TL"): "参考图是南侧朝北的单幅：北侧黑屏大屏幕和木质矮讲台在画面中，东侧落地窗在画面右，西侧会议室玻璃墙在画面左。",
    ("scene-002-s01", "TL"): "参考图是南侧朝北的单幅：北侧后壁和横向扶手在前方，东侧竖排按键在画面右，南侧轿厢门在身后不入画。",
    ("scene-003-s01", "TL"): "参考图是南侧朝北的单幅：北侧三部电梯门和玻璃闸机在前方，东侧旋转门在画面右，西侧白色石材前台在画面左。",
    ("scene-003-s01", "BL"): "参考图是北侧朝南的单幅：南侧咖啡吧柜台和后墙圆形挂钟在画面中，东侧旋转门在画面左，西侧前台在画面右。",
    ("scene-003-s01", "TR"): "参考图是西侧朝东的单幅：东侧玻璃幕墙和旋转门在前方，门外街道和公交候车亭入画，北侧电梯和闸机在画面左。",
    ("scene-004-s01", "TL"): "参考图是南侧朝北的单幅：北侧两部铜色电梯门在前方，东侧玻璃自动门在画面右，西侧木饰面墙和铜牌在画面左。",
    ("scene-005-s01", "TL"): "参考图是南侧朝北的单幅：北侧整面镜面墙和铜色扶手在前方，东侧胡桃木侧壁和按键在画面右，南侧轿厢门在身后不入画。",
    ("scene-006-s01", "TL"): "参考图是南侧朝北的单幅：北侧病床在前方，床头名牌和设备带在画面中，玻璃推拉门在近处，南墙木门在身后不入画。",
    ("scene-007-s01", "TL"): "参考图是南侧朝北的单幅：北墙大屏幕和会议桌北端主位在前方，东侧玻璃墙在画面右，西墙壁挂电视在画面左。",
    ("scene-007-s01", "TR"): "参考图是西侧朝东的单幅：东侧玻璃墙和玻璃门在前方，门外开放办公区工位入画，北墙大屏幕在画面左，南侧矮柜在画面右。",
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
    jobs = sorted((ROOT / "jobs" / "ep_units").glob("EP0[1-6]-寿命掮客-v1-U*"))
    if len(jobs) != 54:
        raise SystemExit(f"expected 54 jobs, got {len(jobs)}")
    for job in jobs:
        assets = job / "assets"
        raw = yaml.safe_load((job / "job.yaml").read_text(encoding="utf-8"))
        fields = raw["fields"]
        unit_key = job.name[:4] + "-" + job.name.rsplit("-", 1)[-1]  # EP01-U01
        panel_wanted = PANEL_BY_UNIT[unit_key]
        crops = []
        for key, rel in fields.items():
            if not key.startswith("ref_image_"):
                continue
            name = Path(str(rel)).name
            if "-scene-" not in name:
                continue
            aid = name.split("-", 1)[1].rsplit(".", 1)[0]
            img = job / str(rel)
            backup_dir = job / "scene_full"
            backup_dir.mkdir(exist_ok=True)
            backup = backup_dir / f"{aid}.png"
            if not backup.exists():
                backup.write_bytes(img.read_bytes())
            crop_panel(backup, panel_wanted, img)
            crops.append((aid, panel_wanted))
        if len(crops) != 1:
            raise SystemExit(f"{job.name}: scene refs {crops}")
        source = (assets / "prompt_source.txt").read_text(encoding="utf-8")
        source = space_dialogue(source)
        lines = source.splitlines()
        changed = 0
        for i, line in enumerate(lines):
            if "@scene-" not in line or "四格" not in line:
                continue
            aid = re.search(r"@(scene-\d+-s\d+)", line, re.I).group(1).lower()
            desc = DESC[(aid, panel_wanted)]
            if "四格参考只用于锁定空间方位，视频画面不出现四格拼版。" in line:
                lines[i] = line.replace(
                    "四格参考只用于锁定空间方位，视频画面不出现四格拼版。", desc)
            else:
                raise SystemExit(f"{job.name}: unexpected scene line: {line[:80]}")
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
