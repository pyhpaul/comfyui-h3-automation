#!/usr/bin/env python3
"""Unpack + audit EP02 trial v3 (latent three-section, timed).

Keeps ▲镜头 clocks and the three latent tails. Does not queue.
Operator notes and Windows paths stay out of the model prompt.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from comfy_orch.named_assets_bind import ensure_bind_line
from comfy_orch.prompt_wire import (
    _body_for_audit,
    audit_pack_prompt_semantics,
    audit_pack_prompt_wiring,
    preflight_job_dir,
    wire_pack_prompt,
)

DOWNLOADS = Path("/mnt/c/Users/lxy/Downloads")
ZIP = DOWNLOADS / "EP02-三阶段试跑-v3-含资产-latent三段式.zip"
OUT = Path("jobs/ep_units")
EPISODE = "EP02-trial-v3-latent"
PACK_KIND = "ep02_trial_latent_append_v1"
_H3_LINE = "【H3 提示词】"
# Spoken lines have a space. Single-word bind labels such as （Recruiter） do not.
_EN_DIALOGUE = re.compile(r"[（(]([A-Za-z][^）)]*\s[^）)]+)[）)]")
_NUMBERED = re.compile(
    r"^(\d+)\.\s*([^（(]+)[（(]((?:char|prop|scene)-\d+[A-Za-z0-9._-]*)\s*[｜|]",
    re.I,
)
_SHOT = re.compile(
    r"▲镜头(\d+)｜\s*(\d+(?:\.\d+)?)\s*[–—-]\s*(\d+(?:\.\d+)?)\s*秒"
)
_LATENT = (
    "【H3 latent 接入文字】",
    "【交出状态】",
    "【H3 latent 接力文字】",
)
_ADAPT_IDS = {
    "scene-009": "广场参考需适配（阴天灰艇/横闩，不是阳光黄金艇与九链紫烟），不能当最终首帧",
    "char-007": "征募考官图是52岁单片镜，原稿是60岁独眼",
    "char-008": "索恩图登记45岁，原稿50岁",
    "char-003": "Vance v5 是细腰佩剑，不能当双手巨剑",
}


def unpack_zip(zip_path: Path) -> Path:
    dest = Path("/tmp") / zip_path.stem
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.unpack_archive(str(zip_path), str(dest))
    root = dest / zip_path.stem
    if (root / "handoff-plan.json").is_file():
        return root
    hits = list(dest.rglob("handoff-plan.json"))
    if not hits:
        raise SystemExit(f"no handoff-plan.json in {zip_path}")
    return hits[0].parent


def extract_h3(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    for i, line in enumerate(lines):
        if line.strip() == _H3_LINE:
            body = "\n".join(lines[i:]).strip()
            return f"{body}\n"
    raise SystemExit("standalone 【H3 提示词】 line missing")


def parse_uploads(text: str) -> list[tuple[str, str, str, str]]:
    """Numbered upload rows only. Returns (id, display, relpath, limit_note)."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("【上传资产路径与顺序】"))
    rows: list[tuple[str, str, str, str]] = []
    i = start + 1
    while i < len(lines) and not lines[i].startswith("【"):
        m = _NUMBERED.match(lines[i].strip())
        if not m:
            i += 1
            continue
        aid = m.group(3).lower()
        display = m.group(2).strip()
        rel = ""
        note = ""
        i += 1
        while i < len(lines) and not _NUMBERED.match(lines[i].strip()) and not lines[i].startswith("【"):
            s = lines[i].strip()
            if s.startswith("本包相对路径："):
                rel = s.split("：", 1)[1].strip().replace("\\", "/")
            elif s.startswith("用途限定："):
                note = s.split("：", 1)[1].strip()
            i += 1
        rows.append((aid, display, rel, note))
    return rows


def bind_display(asset_id: str, display: str) -> str:
    """Keep character Latin names; don't label a prop/detail as the person."""
    m = re.match(r"^([A-Za-z][A-Za-z0-9' -]{1,40})\s+([\u4e00-\u9fff].+)$", display)
    if m and (asset_id.startswith("prop-") or "detail" in asset_id):
        return m.group(2)
    return display


def verify_checksums(pack: Path) -> list[str]:
    issues: list[str] = []
    sums = (pack / "SHA256SUMS.txt").read_text(encoding="utf-8")
    for line in sums.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, rel = line.split(None, 1)
        path = pack / rel.replace("\\", "/")
        if not path.is_file():
            issues.append(f"checksum target missing: {rel}")
            continue
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != digest:
            issues.append(f"checksum mismatch: {rel}")
    return issues


def shot_issues(h3: str, duration: float, overlap: float) -> list[str]:
    shots = [(int(a), float(b), float(c)) for a, b, c in _SHOT.findall(h3)]
    issues: list[str] = []
    if not shots:
        return ["no ▲镜头 clocks"]
    if [n for n, _, _ in shots] != list(range(1, len(shots) + 1)):
        issues.append(f"shot numbers not contiguous: {[n for n, _, _ in shots]}")
    # Overlap second is the latent tail, not a numbered shot. U02+ shots start at 1.00.
    if abs(shots[0][1] - overlap) > 0.001:
        issues.append(f"first shot starts at {shots[0][1]}, expected overlap {overlap}")
    for prev, nxt in zip(shots, shots[1:]):
        if abs(prev[2] - nxt[1]) > 0.001:
            issues.append(f"shot gap {prev[0]}->{nxt[0]}: {prev[2]} != {nxt[1]}")
    if abs(shots[-1][2] - duration) > 0.001:
        issues.append(f"last shot end {shots[-1][2]} != duration {duration}")
    return issues


def write_unit(pack: Path, unit: dict, prompt_path: Path) -> dict:
    uid = unit["id"]
    dur = float(unit["output_duration_seconds"])
    raw = prompt_path.read_text(encoding="utf-8")
    header = raw.replace("\r\n", "\n").split(_H3_LINE, 1)[0]
    m_dur = re.search(r"输出时长：\s*(\d+(?:\.\d+)?)\s*秒", header)
    header_dur = float(m_dur.group(1)) if m_dur else None
    uploads = parse_uploads(raw)
    h3_src = extract_h3(raw)
    entries = [(aid, bind_display(aid, disp)) for aid, disp, _, _ in uploads]
    h3, injected = ensure_bind_line(h3_src, entries)
    body_diff = _body_for_audit(h3_src) != _body_for_audit(
        re.sub(r"^绑定资产：.*$", "", h3, flags=re.M)
    )

    issues: list[str] = []
    warnings: list[str] = []
    if header_dur is None or abs(header_dur - dur) > 0.001:
        issues.append(f"header duration {header_dur} != handoff {dur}")
    if "C:\\" in h3_src or "本包相对路径" in h3_src or "当前解压位置" in h3_src:
        issues.append("operator path leaked into model prompt")
    for marker in _LATENT:
        n = h3_src.count(marker)
        if n != 1:
            issues.append(f"{marker} count={n}")
    issues.extend(shot_issues(h3_src, dur, float(unit.get("overlap_seconds") or 0)))
    bound_body = re.sub(r"^绑定资产：.*$", "", h3, flags=re.M)
    if _EN_DIALOGUE.findall(h3_src) != _EN_DIALOGUE.findall(bound_body):
        issues.append("english dialogue changed while binding")

    staged_meta: list[tuple[str, str, str]] = []
    for aid, _disp, rel, note in uploads:
        if aid == "prop-007" or "需适配参考/prop-007" in rel:
            issues.append("prop-007 crystal was not supposed to be uploaded")
        if not rel or not (pack / rel).is_file():
            issues.append(f"missing upload file {aid} {rel}")
            continue
        staged_meta.append((aid, rel, note))
        if aid in _ADAPT_IDS:
            warnings.append(f"{aid}: {_ADAPT_IDS[aid]}")
        elif "需适配" in note or "待适配" in note or "待补" in note:
            warnings.append(f"{aid}: {note[:80]}")

    if "半人高白水晶" in raw and uid in {"U04", "U05"}:
        warnings.append("半人高白水晶待补，未上传 prop-007 旧水晶")

    job_name = f"{EPISODE}-{uid}"
    job = OUT / job_name
    if job.exists():
        shutil.rmtree(job)
    assets_dir = job / "assets"
    assets_dir.mkdir(parents=True)
    staged: list[str] = []
    for i, (aid, rel, _note) in enumerate(staged_meta):
        dest_name = f"id{i}-{aid}.png"
        shutil.copy2(pack / rel, assets_dir / dest_name)
        staged.append(f"assets/{dest_name}")

    prefix = f"EP02-{uid}-v3-latent"
    fields: dict[str, object] = {
        f"ref_image_{i}": p for i, p in enumerate(staged)
    }
    wired = wire_pack_prompt(h3, {k: str(v) for k, v in fields.items()})
    fields.update(
        {
            "duration_seconds": dur,
            "aspect_ratio": "9:16 (Portrait Widescreen)",
            "megapixels": 1.0,
            "filename_prefix": prefix,
            "prompt": wired,
        }
    )
    refs_all = {k: str(v) for k, v in fields.items() if k.startswith("ref_")}
    w_viol = list(audit_pack_prompt_wiring(h3, wired, refs_all))
    s_viol, s_warn = audit_pack_prompt_semantics(wired, refs_all)
    if _body_for_audit(h3) != _body_for_audit(wired):
        w_viol.append("WIRE_CHANGED_BODY")
    if len(staged) > 9:
        issues.append(f"too many refs: {len(staged)}")
    missing_pic = [i for i in range(1, len(staged) + 1) if f"<Picture {i}>" not in wired]
    if missing_pic:
        issues.append(f"unwired pictures: {missing_pic}")

    parent = unit.get("parent_unit_id")
    (job / "job.yaml").write_text(
        yaml.safe_dump(
            {
                "template": "yz_h3_ep_unit",
                "episode": EPISODE,
                "unit_id": uid,
                "pack_kind": PACK_KIND,
                "parent_unit_id": parent,
                "overlap_seconds": unit.get("overlap_seconds"),
                "scene_cut_after_overlap": unit.get("scene_cut_after_overlap"),
                "fields": fields,
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (assets_dir / "prompt_source.txt").write_text(h3, encoding="utf-8")
    (assets_dir / "prompt_pack_full.txt").write_text(raw, encoding="utf-8")
    (assets_dir / "prompt_h3.txt").write_text(wired, encoding="utf-8")
    pf = preflight_job_dir(job, require_parent_path=True)

    audit = {
        "unit": uid,
        "title": unit.get("name"),
        "job": job_name,
        "duration_seconds": dur,
        "overlap_seconds": unit.get("overlap_seconds"),
        "parent_unit_id": parent,
        "scene_cut_after_overlap": unit.get("scene_cut_after_overlap"),
        "upload_ids": [a for a, _, _, _ in uploads],
        "staged": [{"picture": i + 1, "asset_id": a, "source": r} for i, (a, r, _) in enumerate(staged_meta)],
        "bind_line_injected": injected,
        "body_diff_beyond_bind": body_diff,
        "dialogues": _EN_DIALOGUE.findall(h3_src),
        "shot_count": len(_SHOT.findall(h3_src)),
        "issues": issues,
        "asset_warnings": warnings,
        "wiring_violations": w_viol,
        "semantic_violations": s_viol,
        "semantic_warnings": s_warn,
        "preflight_ok": pf["ok"],
        "reordered": False,
        "unbound_at_tokens": [],
    }
    (assets_dir / "prompt_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    hard = (not pf["ok"]) or issues or s_viol or w_viol or body_diff
    flag = "FAIL" if hard else ("WARN" if warnings or s_warn else "OK")
    pics = " ".join(f"P{i+1}={a}" for i, (a, _, _) in enumerate(staged_meta))
    print(
        f"{flag} {job_name} {unit.get('name')} dur={dur}s overlap={unit.get('overlap_seconds')} "
        f"parent={parent} shots={audit['shot_count']} refs={len(staged)} inject={injected}"
    )
    print(f"  {pics}")
    if audit["dialogues"]:
        print("  dialogue:", " | ".join(audit["dialogues"]))
    for w in warnings:
        print("  ADAPT", w)
    for item in issues:
        print("  ISSUE", item)
    for v in w_viol:
        print("  WIRE", v)
    for v in s_viol:
        print("  SEM-FAIL", v)
    for w in s_warn:
        print("  SEM-WARN", w[:160])
    return audit


def main() -> int:
    pack = unpack_zip(ZIP)
    plan = json.loads((pack / "handoff-plan.json").read_text(encoding="utf-8"))
    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    print("=== PACK ===")
    print("schema", manifest.get("schema") or manifest.get("schema_id"))
    print("status", manifest.get("status"))
    print("release_gate", manifest.get("official_release_gate_pass_claim"))
    checksum_issues = verify_checksums(pack)
    if checksum_issues:
        print("CHECKSUM FAIL", len(checksum_issues))
        for item in checksum_issues[:8]:
            print(" ", item)
    else:
        print("checksums ok")

    prompts = {p.name.split("-", 1)[0]: p for p in (pack / "prompts").glob("U*.txt")}
    rows = []
    for unit in plan["units"]:
        path = prompts.get(unit["id"])
        if path is None:
            raise SystemExit(f"missing prompt for {unit['id']}")
        rows.append(write_unit(pack, unit, path))

    seen: list[str] = []
    for row in rows:
        seen.extend(row["dialogues"])
    plan_lines = [d["text"] for d in plan["dialogues"].values()]
    dialogue_issues = []
    if seen != plan_lines and sorted(seen) != sorted(plan_lines):
        dialogue_issues.append(f"dialogue set mismatch pack={seen} plan={plan_lines}")
    missing_plan = [t for t in plan_lines if t not in seen]
    extra = [t for t in seen if t not in plan_lines]
    if missing_plan or extra or len(seen) != len(plan_lines):
        dialogue_issues.append(f"missing={missing_plan} extra={extra} count={len(seen)}/{len(plan_lines)}")

    report = Path("runs/ep02_trial_v3_latent_unpack_audit.json")
    report.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "checksum_issues": checksum_issues,
        "dialogue_issues": dialogue_issues,
        "units": rows,
        "not_queued": True,
        "notime_stripped": False,
    }
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    ok_n = sum(1 for r in rows if r["preflight_ok"] and not r["issues"] and not r["wiring_violations"] and not r["semantic_violations"] and not r["body_diff_beyond_bind"])
    print(f"\nreport {report} clean={ok_n}/{len(rows)} dialogue_issues={len(dialogue_issues)} checksum_issues={len(checksum_issues)}")

    proc = subprocess.run(
        [sys.executable, "scripts/audit_pack_prompts.py", "--glob", f"{EPISODE}-U*"],
        capture_output=True,
        text=True,
    )
    print("=== formal audit exit", proc.returncode, "===")
    for ln in (proc.stdout + proc.stderr).splitlines():
        if any(x in ln for x in ("PASS", "FAIL", "WARN", "units", "OK")):
            print(ln)
    failed = ok_n != len(rows) or checksum_issues or dialogue_issues or proc.returncode != 0
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
