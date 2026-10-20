#!/usr/bin/env python3
"""Create official-skill-optimized copies of the EP17/EP18 wenwu test jobs.

Originals stay untouched. Copies get the `-wenwuopt` prefix and only the
minimal edits from docs/ops/2026-10-20-ep17-ep18-official-skill-prompt-scan.md:
  1. listener lips-closed locks on the two flagged dialogue shots
     (EP18-U03 Liam, EP18-U08 Cain);
  2. operator meta / "调度假设" clauses rewritten as locked statements;
  3. EP18-U05 duplicated cross-episode state block deduplicated.
prompt_h3.txt and job.yaml fields.prompt are re-wired from the edited source.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comfy_orch.prompt_wire import wire_pack_prompt  # noqa: E402

JOB_ROOT = ROOT / "jobs" / "ep_units_wenwu_test"
EPISODES = ["EP17-兽王降临-wenwu", "EP18-秘银碎裂-wenwu"]

META_EDITS = [
    ("上述方位及通行带是待四方位图验证的调度假设。",
     "上述方位及通行带全程锁定，不得变更。"),
    ("具体通视角是调度假设。", "通视角按此锁定。"),
    ("空间拓扑为本轮明确给定、待新四方位图核验的假设。",
     "空间拓扑按此锁定，全程不变。"),
]


def edit_source(text: str, job_name: str, log: list[str]) -> str:
    out = text
    for old, new in META_EDITS:
        n = out.count(old)
        if n:
            out = out.replace(old, new)
            log.append(f"{job_name}: meta x{n}: {old[:18]}… -> locked")
    if job_name.endswith("EP18-秘银碎裂-wenwuopt-U03"):
        old = "Liam 的站位和夹刃姿势保持稳定。"
        assert out.count(old) == 1
        out = out.replace(old, old + "Liam 嘴唇合上、闭口无声，禁止口型。")
        log.append(f"{job_name}: +Liam lips-closed lock (Cain dialogue shot)")
    if job_name.endswith("EP18-秘银碎裂-wenwuopt-U08"):
        old = "凹陷胸甲、断鼻与涕泪泥污持续保留。"
        assert out.count(old) == 1
        out = out.replace(old, old + "Cain 嘴唇合上、闭口无声，禁止口型。")
        log.append(f"{job_name}: +Cain lips-closed lock (Liam dialogue shot)")
    if job_name.endswith("EP18-秘银碎裂-wenwuopt-U05"):
        paras = out.split("\n")
        seen = set()
        kept, dropped = [], 0
        for line in paras:
            key = line.strip()
            if key.startswith("跨集既有状态持续") and key in seen:
                dropped += 1
                continue
            if key.startswith("跨集既有状态持续"):
                seen.add(key)
            kept.append(line)
        out = "\n".join(kept)
        log.append(f"{job_name}: dedup cross-episode state blocks x{dropped}")
    return out


def main() -> int:
    log: list[str] = []
    for ep in EPISODES:
        for src in sorted(JOB_ROOT.glob(f"{ep}-U*")):
            if not src.is_dir():
                continue
            dst = JOB_ROOT / src.name.replace("-wenwu-", "-wenwuopt-", 1)
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            source_path = dst / "assets" / "prompt_source.txt"
            new_source = edit_source(
                source_path.read_text(encoding="utf-8"), dst.name, log)
            source_path.write_text(new_source, encoding="utf-8")
            job_yaml_path = dst / "job.yaml"
            job_yaml = yaml.safe_load(job_yaml_path.read_text(encoding="utf-8"))
            job_yaml["pack_kind"] = str(job_yaml.get("pack_kind")) + "_opt"
            fields = job_yaml["fields"]
            refs = {k: v for k, v in fields.items() if k.startswith("ref_image_")}
            wired = wire_pack_prompt(new_source, refs)
            fields["prompt"] = wired
            job_yaml_path.write_text(
                yaml.safe_dump(job_yaml, allow_unicode=True, sort_keys=False,
                               width=1000), encoding="utf-8")
            (dst / "assets" / "prompt_h3.txt").write_text(wired, encoding="utf-8")
            audit_path = dst / "assets" / "prompt_audit.json"
            if audit_path.is_file():
                audit = json.loads(audit_path.read_text(encoding="utf-8"))
                audit["optimized_variant"] = True
                audit_path.write_text(
                    json.dumps(audit, ensure_ascii=False, indent=2),
                    encoding="utf-8")
            print(f"OPT {dst.name}")
    report = ROOT / "runs" / "ep17_ep18_opt_prompt_edits.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("# EP17/EP18 optimized-prompt edits\n\n" +
                      "\n".join(f"- {x}" for x in log) + "\n", encoding="utf-8")
    print(f"edits={len(log)} report={report}")
    for line in log:
        print(" ", line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
