#!/usr/bin/env python3
"""Unpack + audit EP04 H3 manual-call named-assets pack (ep07 layout + ep08 v4.6 quality)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from comfy_orch.named_assets_bind import ensure_bind_line
from comfy_orch.prompt_wire import (
    _bare_name,
    _body_for_audit,
    _picture1_identity_name,
    _shot1_lead_name,
    audit_pack_prompt_semantics,
    audit_pack_prompt_wiring,
    preflight_job_dir,
    wire_pack_prompt,
)

DOWNLOADS = Path("/mnt/c/Users/lxy/Downloads")
ZIP = DOWNLOADS / "EP04-H3-manual-call-package-v1_6-ep08-v4_6-20260917.zip"
OUT = Path("jobs/ep_units")
_H3 = "【H3 提示词】"
_AT = re.compile(r"@(char|prop|scene)-([A-Za-z0-9._-]+)\b", re.I)
_ASSET_IN_LINE = re.compile(
    r"^(\d+)\.\s*([^（(]+)[（(]((?:char|prop|scene)-\d+[A-Za-z0-9._-]*)\s*[｜|]",
    re.I,
)
_TITLE_FROM_PROMPT = re.compile(r"prompts/(U\d+)-(.+)\.txt$", re.I)
NAME_TO_HINTS = {
    "alden": ["alden", "char-002", "char-013"],
    "liam": ["liam", "char-001"],
    "vivian": ["vivian", "char-004"],
    "vance": ["vance", "char-003"],
    "gorke": ["gorke", "char-012"],
    "mia": ["mia", "char-002"],
    "drake": ["drake", "char-006", "shadow"],
}


def unpack_zip(zip_path: Path) -> Path:
    stem = zip_path.stem
    dest = Path("/tmp") / stem
    unpack = DOWNLOADS / f"{stem}-unpacked"
    for d in (dest, unpack):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
    shutil.unpack_archive(str(zip_path), str(dest))
    shutil.unpack_archive(str(zip_path), str(unpack))
    if (dest / "package-manifest.json").is_file():
        return dest
    mans = list(dest.rglob("package-manifest.json"))
    if not mans:
        raise SystemExit("no manifest")
    return mans[0].parent


def extract_h3(text: str) -> str:
    if _H3 not in text:
        raise SystemExit("missing H3")
    return f"{_H3}\n{text.split(_H3, 1)[1].strip()}\n"


def parse_upload_entries(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    in_sec = False
    for line in text.splitlines():
        if line.startswith("【上传资产路径与顺序】"):
            in_sec = True
            continue
        if in_sec and line.startswith("【"):
            break
        if not in_sec or not line.strip():
            continue
        m = _ASSET_IN_LINE.search(line)
        if m:
            out.append((m.group(3).lower(), m.group(2).strip()))
            continue
        m2 = re.search(r"\b((?:char|prop|scene)-\d+[A-Za-z0-9._-]*)\b", line, re.I)
        if m2:
            out.append((m2.group(1).lower(), m2.group(1)))
    return out


def unit_title(prompt_rel: str, raw: str) -> str:
    m = _TITLE_FROM_PROMPT.search(prompt_rel.replace("\\", "/"))
    if m:
        return m.group(2)
    m2 = re.search(r"U\d+\s*[｜|]\s*([^｜|\n]+)", raw)
    return m2.group(1).strip() if m2 else prompt_rel


def intentional_unbound(h3: str, tok: str) -> bool:
    if re.search(rf"不绑定[^。\n]{{0,80}}@{re.escape(tok)}", h3, re.I):
        return True
    if re.search(rf"现有\s*`?@{re.escape(tok)}`?[^。\n]{{0,40}}禁止", h3, re.I):
        return True
    for m in re.finditer(rf"`?@{re.escape(tok)}`?", h3, re.I):
        window = h3[max(0, m.start() - 80) : m.end() + 80]
        if any(k in window for k in ("不绑定", "禁止", "不上传", "纯文字")):
            return True
    return False


def stem_of(path: str) -> str:
    return Path(_bare_name(path)).stem.lower()


def match_lead(lead: str, path: str) -> bool:
    stem = stem_of(path)
    hints = NAME_TO_HINTS.get(lead.casefold(), [lead.casefold()])
    return any(h in stem for h in hints)


def reorder_for_shot1(paths: list[str], source: str, wired: str) -> list[str]:
    if "【镜头1" in wired:
        s1 = wired.split("【镜头1", 1)[1]
        s1 = s1.split("【镜头2", 1)[0] if "【镜头2" in s1 else s1
        if "【无脸表演豁免】" in s1:
            return paths
    lead, closeup = _shot1_lead_name(wired)
    if not lead or not closeup:
        return paths
    lead_idx = next((i for i, p in enumerate(paths) if match_lead(lead, p)), None)
    if lead_idx is None or lead_idx == 0:
        return paths
    return [paths[lead_idx]] + [p for i, p in enumerate(paths) if i != lead_idx]


def resolve_unit_assets(asset_index: dict, upload_ids: list[str]):
    out, missing = [], []
    for aid in upload_ids:
        hit = asset_index.get(aid)
        if not hit:
            for k, v in asset_index.items():
                if (
                    k.startswith(aid)
                    or aid.startswith(k)
                    or k.startswith(aid + "-")
                    or aid.startswith(k + "-")
                ):
                    hit = v
                    break
        if not hit:
            missing.append(aid)
            continue
        out.append((hit["asset_id"], hit["path"]))
    return out, missing


def strip_parens_for_compare(t: str) -> str:
    return re.sub(r"[（(][^）)]*[）)]", "（）", t)


def main() -> int:
    pack = unpack_zip(ZIP)
    man = json.loads((pack / "package-manifest.json").read_text(encoding="utf-8"))
    episode = "EP04-H3-manual-v16"
    pack_kind = "ep04_manual_v16_ep08_v46"
    report = Path("runs/ep04_manual_v16_unpack_audit.json")
    asset_index = {a["asset_id"].lower(): a for a in man["assets"]}

    print("=== PACK ===")
    print("package", man.get("package"))
    print("format", man.get("format_profile"), "quality", man.get("quality_rule_profile"))
    print("units", len(man["units"]), "assets", len(man["assets"]))
    print("assets", [a["asset_id"] for a in man["assets"]])

    rows = []
    for unit in man["units"]:
        uid = unit["unit_id"]
        dur = int(unit["duration_seconds"])
        raw = (pack / unit["prompt"]).read_text(encoding="utf-8")
        title = unit_title(unit["prompt"], raw)
        upload_entries = parse_upload_entries(raw)
        upload_ids = [a for a, _ in upload_entries]
        raw_h3 = extract_h3(raw)
        h3, injected = ensure_bind_line(raw_h3, upload_entries)
        a = _body_for_audit(strip_parens_for_compare(raw_h3))
        b = _body_for_audit(
            strip_parens_for_compare(re.sub(r"^绑定资产：.*$", "", h3, flags=re.M))
        )
        body_diff = a != b
        manifest_assets, missing = resolve_unit_assets(asset_index, upload_ids)
        issues: list[str] = []
        if missing:
            issues.append(f"missing asset ids: {missing}")
        for aid, rel in manifest_assets:
            if not (pack / rel).is_file():
                issues.append(f"missing file {rel}")
        at_tokens = sorted({f"{a}-{b}".lower() for a, b in _AT.findall(h3)})
        unbound = []
        for tok in at_tokens:
            ok = any(
                aid.lower() == tok
                or aid.lower().startswith(tok + "-")
                or tok.startswith(aid.lower())
                for aid, _ in manifest_assets
            )
            if not ok and not intentional_unbound(h3, tok):
                unbound.append(tok)

        job = OUT / f"{episode}-{uid}"
        if job.exists():
            shutil.rmtree(job)
        assets_dir = job / "assets"
        assets_dir.mkdir(parents=True)
        staged: list[str] = []
        for i, (aid, rel) in enumerate(manifest_assets):
            dest_name = f"id{i}-{Path(rel).name}"
            shutil.copy2(pack / rel, assets_dir / dest_name)
            staged.append(f"assets/{dest_name}")

        wired0 = wire_pack_prompt(h3, {f"ref_image_{i}": p for i, p in enumerate(staged)})
        new_paths = reorder_for_shot1(staged, h3, wired0)
        fields = {f"ref_image_{i}": p for i, p in enumerate(new_paths)}
        fields.update(
            {
                "duration_seconds": dur,
                "aspect_ratio": "9:16 (Portrait Widescreen)",
                "megapixels": 1.0,
                "filename_prefix": f"EP04-{uid}-v16",
            }
        )
        wired = wire_pack_prompt(h3, {k: v for k, v in fields.items() if k.startswith("ref_")})
        fields["prompt"] = wired
        refs_all = {k: v for k, v in fields.items() if k.startswith("ref_")}
        w_viol = list(audit_pack_prompt_wiring(h3, wired, refs_all))
        s_viol, s_warn = audit_pack_prompt_semantics(
            wired, {k: v for k, v in fields.items() if k.startswith("ref_image_")}
        )
        if _body_for_audit(h3) != _body_for_audit(wired):
            w_viol.append("WIRE_CHANGED_BODY")

        (job / "job.yaml").write_text(
            yaml.safe_dump(
                {
                    "template": "yz_h3_ep_unit",
                    "episode": episode,
                    "unit_id": uid,
                    "pack_kind": pack_kind,
                    "parent_unit_id": unit.get("parent_unit_id"),
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
        lead, closeup = _shot1_lead_name(wired)
        p1 = _picture1_identity_name(wired)

        asset_mismatch = []
        for i, (aid, rel) in enumerate(manifest_assets):
            bare = re.sub(r"^id\d+-", "", Path(new_paths[i]).name)
            if aid.lower() not in bare.lower():
                asset_mismatch.append({"slot": i + 1, "asset_id": aid, "file": bare})

        audit = {
            "unit": uid,
            "title": title,
            "duration_seconds": dur,
            "parent_unit_id": unit.get("parent_unit_id"),
            "upload_ids": upload_ids,
            "bind_line_injected": injected,
            "body_diff_beyond_bind": body_diff,
            "manifest_upload": [{"asset_id": a, "path": p} for a, p in manifest_assets],
            "staged": [{"picture": i + 1, "job_path": p} for i, p in enumerate(new_paths)],
            "asset_mismatch": asset_mismatch,
            "reordered": new_paths != staged,
            "at_tokens": at_tokens,
            "unbound_at_tokens": unbound,
            "issues": issues,
            "shot1_lead": lead,
            "shot1_closeup": closeup,
            "picture1_identity": p1,
            "wiring_violations": w_viol,
            "semantic_violations": s_viol,
            "semantic_warnings": s_warn,
            "preflight_ok": pf["ok"],
            "has_no_face_exemption": "【无脸表演豁免】" in h3,
        }
        (assets_dir / "prompt_audit.json").write_text(
            json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        rows.append(audit)
        hard = (
            (not pf["ok"])
            or issues
            or s_viol
            or w_viol
            or unbound
            or asset_mismatch
            or body_diff
        )
        flag = "FAIL" if hard else ("WARN" if s_warn else "OK")
        bind = " | ".join(f"P{x['picture']}={Path(x['job_path']).name}" for x in audit["staged"])
        print(
            f"{flag} {uid} {title} refs={len(new_paths)} inject={injected} "
            f"reorder={audit['reordered']} body_diff={body_diff}"
        )
        print(f"  {bind}")
        if issues:
            print("  ISSUES", issues)
        if unbound:
            print("  UNBOUND", unbound)
        if asset_mismatch:
            print("  ASSET-MISMATCH", asset_mismatch)
        for v in w_viol:
            print("  WIRE", v)
        for v in s_viol:
            print("  SEM-FAIL", v)
        for w in s_warn:
            print("  SEM-WARN", w[:140])

    report.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    ok_n = sum(
        1
        for r in rows
        if r["preflight_ok"]
        and not r["semantic_violations"]
        and not r["unbound_at_tokens"]
        and not r["issues"]
        and not r["wiring_violations"]
        and not r["asset_mismatch"]
        and not r["body_diff_beyond_bind"]
    )
    print(f"\nreport {report} clean={ok_n}/{len(rows)}")

    r = subprocess.run(
        [sys.executable, "scripts/audit_pack_prompts.py", "--glob", "EP04-H3-manual-v16-U*"],
        capture_output=True,
        text=True,
    )
    print("=== formal audit exit", r.returncode, "===")
    for ln in (r.stdout + r.stderr).splitlines():
        if any(x in ln for x in ("PASS", "FAIL", "WARN", "units")):
            print(ln)
    return 0 if ok_n == len(rows) and r.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
