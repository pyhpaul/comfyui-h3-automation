#!/usr/bin/env python3
"""Unpack + audit EP17《兽王降临》/ EP18《秘银碎裂》wenwu-test packs.

Source: Feiniu inbox `comfyul （文武工作流测试）` zips, staged under
.cache/wenwu_test_pack/. Jobs land in jobs/ep_units_wenwu_test with
template yz_h3_wenwu_test so run_wenwu_test_ep_units.py can pick them up.
Does not queue.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from comfy_orch.named_assets_bind import ensure_bind_line  # noqa: E402
from comfy_orch.prompt_wire import (  # noqa: E402
    _body_for_audit,
    audit_pack_prompt_semantics,
    audit_pack_prompt_wiring,
    preflight_job_dir,
    wire_pack_prompt,
)
from unpack_ep01_dead_v1 import extract_h3  # noqa: E402

OUT = ROOT / "jobs" / "ep_units_wenwu_test"
PACKS = [
    ("EP17", "EP17-兽王降临", ".cache/wenwu_test_pack/EP17-H3-manual-call-package-v1.zip"),
    ("EP18", "EP18-秘银碎裂", ".cache/wenwu_test_pack/EP18-H3-manual-call-package-v1.zip"),
]
_EN_DIALOGUE = re.compile(r"[（(]([A-Za-z][^）)]*\s[^）)]+)[）)]")
_AT = re.compile(r"@(char|prop|scene)-([A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*)", re.I)
_LATENT = ("【H3 latent 接入文字】", "【交出状态】", "【H3 latent 接力文字】")


def parse_uploads(text: str, asset_ids: list[str]) -> list[tuple[str, str]]:
    """Manifest order; display name from the pack upload block itself."""
    head = text.replace("\r\n", "\n").split("【H3 提示词】", 1)[0]
    out: list[tuple[str, str]] = []
    for aid in asset_ids:
        key = aid.lower()
        disp = aid
        for line in head.splitlines():
            if key in line.lower() and line.strip()[:1].isdigit():
                disp = line.split("（", 1)[0].split(".", 1)[-1].strip() or disp
                break
        if key not in head.lower():
            raise SystemExit(f"{aid} missing from upload block")
        out.append((key, disp))
    return out


def write_unit(pack: Path, unit: dict, asset_index: dict, *, episode: str,
               pack_kind: str, file_head: str) -> dict:
    uid = unit["unit_id"]
    dur = float(unit["duration_seconds"])
    raw = (pack / unit["prompt"]).read_text(encoding="utf-8")
    uploads = parse_uploads(raw, list(unit.get("asset_ids") or []))
    h3_src = extract_h3(raw)
    h3, injected = ensure_bind_line(h3_src, uploads)
    body_diff = _body_for_audit(h3_src) != _body_for_audit(
        re.sub(r"^绑定资产：.*$", "", h3, flags=re.M)
    )
    issues: list[str] = []
    warnings: list[str] = []
    if "E:\\" in h3_src or "C:\\" in h3_src:
        issues.append("operator path leaked into model prompt")
    start_mode = str(unit.get("start_mode") or "")
    relay = "【H3 latent 接力文字】"
    if start_mode == "independent":
        expected = {m: 0 for m in _LATENT}
    else:
        expected = {m: 1 for m in _LATENT}
        if start_mode == "parent_latent" and unit.get("expects_handoff") is False:
            expected[relay] = 0
    for marker in _LATENT:
        count = h3_src.count(marker)
        if count != expected[marker]:
            issues.append(f"{marker} count={count}")
    if "【镜头" in h3_src:
        issues.append("unexpected per-shot clocks in light pack")
    if _EN_DIALOGUE.findall(h3_src) != _EN_DIALOGUE.findall(h3):
        issues.append("english dialogue changed while binding")
    if [a for a, _ in uploads] != [a.lower() for a in unit.get("asset_ids") or []]:
        issues.append("upload order != manifest asset_ids")

    staged_meta: list[tuple[str, str]] = []
    for aid, _disp in uploads:
        hit = asset_index.get(aid)
        if not hit:
            issues.append(f"missing asset id {aid}")
            continue
        rel = str(hit.get("path") or hit.get("file") or "")
        if not (pack / rel).is_file():
            issues.append(f"missing file {rel}")
            continue
        staged_meta.append((aid, rel))

    job_name = f"{episode}-wenwu-{uid}"
    job = OUT / job_name
    if job.exists():
        shutil.rmtree(job)
    assets_dir = job / "assets"
    assets_dir.mkdir(parents=True)
    staged: list[str] = []
    for i, (aid, rel) in enumerate(staged_meta):
        dest_name = f"id{i}-{aid}.png"
        shutil.copy2(pack / rel, assets_dir / dest_name)
        staged.append(f"assets/{dest_name}")

    fields: dict[str, object] = {f"ref_image_{i}": p for i, p in enumerate(staged)}
    wired = wire_pack_prompt(h3, {k: str(v) for k, v in fields.items()})
    fields.update({
        "duration_seconds": dur,
        "aspect_ratio": "9:16 (Portrait Widescreen)",
        "megapixels": 1.0,
        "filename_prefix": f"{file_head}-{uid}-wenwu",
        "prompt": wired,
    })
    refs = {k: str(v) for k, v in fields.items() if k.startswith("ref_")}
    w_viol = list(audit_pack_prompt_wiring(h3, wired, refs))
    s_viol, s_warn = audit_pack_prompt_semantics(wired, refs)
    if _body_for_audit(h3) != _body_for_audit(wired):
        w_viol.append("WIRE_CHANGED_BODY")
    at_tokens = sorted({f"{a}-{b}".lower() for a, b in _AT.findall(h3)})
    unbound = [t for t in at_tokens if not any(a == t for a, _ in staged_meta)]
    missing_pic = [i for i in range(1, len(staged) + 1) if f"<Picture {i}>" not in wired]
    if missing_pic:
        issues.append(f"unwired pictures {missing_pic}")
    if len(staged) > 9:
        issues.append(f"too many refs {len(staged)}")
    scene_ids = [a for a, _ in staged_meta if a.startswith("scene-")]
    if len(scene_ids) > 1:
        warnings.append(f"multiple scene refs bound: {scene_ids}")

    (job / "job.yaml").write_text(yaml.safe_dump({
        "template": "yz_h3_wenwu_test",
        "episode": episode,
        "unit_id": uid,
        "pack_kind": pack_kind,
        "parent_unit_id": unit.get("parent_unit_id"),
        "start_mode": unit.get("start_mode"),
        "fields": fields,
    }, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (assets_dir / "prompt_source.txt").write_text(h3, encoding="utf-8")
    (assets_dir / "prompt_pack_full.txt").write_text(raw, encoding="utf-8")
    (assets_dir / "prompt_h3.txt").write_text(wired, encoding="utf-8")
    pf = preflight_job_dir(job, require_parent_path=True)
    audit = {
        "unit": uid, "job": job_name, "duration_seconds": dur,
        "parent_unit_id": unit.get("parent_unit_id"), "start_mode": start_mode,
        "upload_ids": [a for a, _ in uploads],
        "staged": [{"picture": i + 1, "asset_id": a, "source": r}
                   for i, (a, r) in enumerate(staged_meta)],
        "bind_line_injected": injected, "body_diff_beyond_bind": body_diff,
        "dialogues": _EN_DIALOGUE.findall(h3_src),
        "issues": issues, "asset_warnings": warnings,
        "unbound_at_tokens": unbound, "wiring_violations": w_viol,
        "semantic_violations": s_viol, "semantic_warnings": s_warn,
        "preflight_ok": pf["ok"], "light_pack": True, "notime_stripped": False,
    }
    (assets_dir / "prompt_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    hard = (not pf["ok"]) or issues or s_viol or w_viol or unbound or body_diff
    flag = "FAIL" if hard else ("WARN" if warnings or s_warn else "OK")
    print(f"{flag} {job_name} dur={dur}s parent={unit.get('parent_unit_id')} "
          f"start={start_mode} refs={len(staged)} inject={injected}")
    print("  " + " ".join(f"P{i+1}={a}" for i, (a, _) in enumerate(staged_meta)))
    for item in issues + unbound + w_viol + s_viol:
        print("  ISSUE", item)
    for w in warnings:
        print("  ADAPT", w)
    for w in s_warn:
        print("  SEM-WARN", str(w)[:160])
    return audit


def main() -> int:
    all_rows: list[dict] = []
    job_dirs: list[str] = []
    for file_head, episode, zip_rel in PACKS:
        zip_path = ROOT / zip_rel
        dest = Path("/tmp") / zip_path.stem
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        shutil.unpack_archive(str(zip_path), str(dest))
        pack = next(dest.rglob("package-manifest.json")).parent
        man = json.loads((pack / "package-manifest.json").read_text(encoding="utf-8"))
        asset_index = {a["asset_id"].lower(): a for a in man["assets"]}
        print("=== PACK ===", man.get("package"), man.get("title"),
              "units", len(man["units"]))
        units = man["units"]
        prepared = []
        for index, unit in enumerate(units):
            row = dict(unit)
            nxt = units[index + 1]["start_mode"] if index + 1 < len(units) else None
            if row.get("start_mode") == "parent_latent":
                row["expects_handoff"] = nxt == "parent_latent"
            prepared.append(row)
        rows = [write_unit(pack, u, asset_index, episode=episode,
                           pack_kind=f"{file_head.lower()}_wenwu_test",
                           file_head=file_head) for u in prepared]
        all_rows.extend(rows)
        job_dirs.extend(str(OUT / r["job"]) for r in rows)
        report = ROOT / "runs" / f"{file_head.lower()}_wenwu_unpack_audit.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({"units": rows}, ensure_ascii=False, indent=2),
                          encoding="utf-8")
        print(f"report {report}")

    proc = subprocess.run(
        [sys.executable, "scripts/audit_pack_prompts.py", *job_dirs],
        capture_output=True, text=True, cwd=ROOT)
    print("=== formal audit exit", proc.returncode, "===")
    print(proc.stdout[-4000:])
    if proc.returncode != 0:
        print(proc.stderr[-2000:])
    clean = sum(1 for r in all_rows if r["preflight_ok"] and not r["issues"]
                and not r["wiring_violations"] and not r["semantic_violations"]
                and not r["unbound_at_tokens"] and not r["body_diff_beyond_bind"])
    print(f"clean={clean}/{len(all_rows)} not_queued=True")
    return 0 if clean == len(all_rows) and proc.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
