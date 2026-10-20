#!/usr/bin/env python3
"""Fix dual-scene fourgrid bindings in EP17-U08 / EP18-U05 (wenwu test).

Each bound scene fourgrid (1696x954, panels labelled 南→北/西→东/北→南/东→西
in TL/TR/BL/BR order) is cropped to the single panel matching the unit's
camera side. Full fourgrids are backed up outside assets/. Only the
fourgrid description sentence in prompt_source.txt is rewritten to
single-panel wording; all other body text is untouched. prompt_h3.txt and
job.yaml fields.prompt are re-wired from the fixed source.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comfy_orch.prompt_wire import preflight_job_dir, wire_pack_prompt  # noqa: E402

# panel crop boxes on 1696x954 (x, y, w, h), 6px inset off the white cross
PANELS = {
    "南→北": (6, 6, 836, 465),
    "西→东": (854, 6, 836, 465),
    "北→南": (6, 483, 836, 465),
    "东→西": (854, 483, 836, 465),
}

FIXES = [
    {
        "job": "EP17-兽王降临-wenwu-U08",
        "crops": [
            # camera: box east side looking west, then arena east side looking west
            ("id4-scene-037.png", "东→西",
             "主看台独立悬挑包厢 @scene-037（scene-037）：包厢在沙场北侧高处，南敞口曲栏面向沙场，北为后门，西为唯一煤气立灯；中央低石案加黄铜酒盘，东西两把深红软椅面南。参考图为包厢东侧向西的单幅视图，只锁定这一侧的空间方位、材质与光源；参考为空场结构，人物、杯碎和Cain离位按逐U动态加入，不恢复完整酒杯。视频画面不出现拼版。"),
            ("id5-scene-035.png", "东→西",
             "辅助场景 连续跳落路径下方的沙场、破口及龙首接触位置 @scene-035（scene-035）：世界北为两根铜鹰柱之间唯一主看台，南为中央兽闸，东/西为弧形花岗岩拱廊；中心沙面周围有石铺边带。参考图为沙场东侧向西的单幅视图，只锁定这一侧的地标拓扑和日光，不把沙面、巨兽、破土孔或战损重置；EP17动态破口和EP18沟槽由各U状态硬锁覆盖。仅用于上述指定的时段或画内区域，不替代本 U 主场景；视频画面不出现拼版。"),
        ],
    },
    {
        "job": "EP18-秘银碎裂-wenwu-U05",
        "crops": [
            # dead-angle segment: low camera south-west of the nook, facing the north wall and east arch
            ("id2-scene-038.png", "南→北",
             "主看台正下方死角 @scene-038（scene-038）：主看台基座下阴影维修死角；世界北为粗凿排水墙，东唯一维修拱通沙场，西扶壁及木撑碎砖，南低石沿和泥沙净道。参考图为死角南侧向北的单幅视图，只锁定这一侧的空间方位、材质与光源；东拱在画面右侧，不重复。静态图未预置撞墙裂痕、血迹或人物，EP18按U加入；Liam从东拱通视线向北上方看包厢，具体通视角是调度假设。视频画面不出现拼版。"),
            # arena segment: camera on the south-west side tracking Cain toward the north stand base
            ("id3-scene-035.png", "南→北",
             "辅助场景 开头倒飞及中段 Liam 自沙场起步；其后硬切主看台下死角，不能按同图连续生成。 @scene-035（scene-035）：世界北为两根铜鹰柱之间唯一主看台，南为中央兽闸，东/西为弧形花岗岩拱廊；中心沙面周围有石铺边带。参考图为沙场南侧向北的单幅视图，只锁定这一侧的地标拓扑和日光，不把沙面、巨兽、破土孔或战损重置；EP17动态破口和EP18沟槽由各U状态硬锁覆盖。仅用于上述指定的时段或画内区域，不替代本 U 主场景；视频画面不出现拼版。"),
        ],
    },
]


def crop_panel(src: Path, panel: str, dest: Path) -> None:
    x, y, w, h = PANELS[panel]
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(src), "-vf",
         f"crop={w}:{h}:{x}:{y}", "-frames:v", "1", "-y", str(dest)],
        check=True)


def main() -> int:
    for fix in FIXES:
        job = ROOT / "jobs" / "ep_units_wenwu_test" / fix["job"]
        assets = job / "assets"
        source_path = assets / "prompt_source.txt"
        source = source_path.read_text(encoding="utf-8")
        for fname, panel, _replacement in fix["crops"]:
            img = assets / fname
            backup = job / f"{img.stem}-fourgrid-full.png"
            if not backup.exists():
                backup.write_bytes(img.read_bytes())
            crop_panel(backup, panel, img)
            print(f"CROP {fix['job']}/{fname} -> {panel} (backup {backup.name})")
        # swap the fourgrid description sentences for single-panel wording
        lines = source.splitlines()
        changed = 0
        for i, line in enumerate(lines):
            for fname, _panel, replacement in fix["crops"]:
                aid = fname.split("-", 1)[1].rsplit(".", 1)[0]
                if f"@{aid}" in line and "四格" in line:
                    lines[i] = replacement
                    changed += 1
        if changed != len(fix["crops"]):
            raise SystemExit(f"{fix['job']}: replaced {changed} scene lines, "
                             f"expected {len(fix['crops'])}")
        new_source = "\n".join(lines).rstrip() + "\n"
        source_path.write_text(new_source, encoding="utf-8")

        job_yaml_path = job / "job.yaml"
        job_yaml = yaml.safe_load(job_yaml_path.read_text(encoding="utf-8"))
        fields = job_yaml["fields"]
        refs = {k: v for k, v in fields.items() if k.startswith("ref_image_")}
        wired = wire_pack_prompt(new_source, refs)
        fields["prompt"] = wired
        job_yaml_path.write_text(
            yaml.safe_dump(job_yaml, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
        (assets / "prompt_h3.txt").write_text(wired, encoding="utf-8")

        audit_path = assets / "prompt_audit.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        audit["scene_crop_fix"] = {
            "crops": [{"file": f, "panel": p} for f, p, _ in fix["crops"]],
            "note": "dual-scene fourgrids cropped to camera-side panel; "
                    "fourgrid sentences rewritten to single-panel wording",
        }
        audit["asset_warnings"] = [
            w for w in audit.get("asset_warnings", [])
            if not w.startswith("multiple scene refs")]
        audit_path.write_text(
            json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
        pf = preflight_job_dir(job, require_parent_path=True)
        print(f"FIXED {fix['job']} preflight_ok={pf['ok']}")
        if not pf["ok"]:
            print(pf)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
