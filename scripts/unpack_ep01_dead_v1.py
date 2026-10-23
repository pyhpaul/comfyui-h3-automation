#!/usr/bin/env python3
"""Unpack EP01《死人回来了》H3 light manual-call v1.

Light pack: unit duration only, no per-shot clocks. Keeps prompt text.
Resolves assets from package-manifest paths, never Windows paths.
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

from comfy_orch.named_assets_bind import ensure_bind_line
from comfy_orch.prompt_wire import (
    _body_for_audit,
    audit_pack_prompt_semantics,
    audit_pack_prompt_wiring,
    preflight_job_dir,
    wire_pack_prompt,
)

ZIP = Path("/mnt/c/Users/lxy/Downloads/EP01-H3-manual-call-package-v1.zip")
OUT = Path("jobs/ep_units")
# Per-unit-duration packs (duration_policy=per_unit_content_v1) set this to
# None; the fixed 15.083s light-pack check is skipped then.
EXPECTED_DURATION: float | None = 15.083
EPISODE = "EP01-死人回来了-v1"
PACK_KIND = "ep01_dead_v1"
FILE_HEAD = "EP01"
FILE_TAG = "dead"
_H3 = "【H3 提示词】"
_EN_DIALOGUE = re.compile(r"[（(]([A-Za-z][^）)]*\s[^）)]+)[）)]")
_AT = re.compile(
    r"@(char|prop|scene)-([A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*)",
    re.I,
)
_LATENT = (
    "【H3 latent 接入文字】",
    "【交出状态】",
    "【H3 latent 接力文字】",
)

_LABEL = {
    "char-001": "Ava",
    "char-002-w01": "Sloane",
    "char-003": "Tate",
    "char-004": "Victor",
    "char-005": "Dax",
    "char-101": "Guard",
    "char-102": "GuardMate",
    "char-103": "NecklaceGuest",
    "char-104": "Clerk",
    "char-105": "DaxMateA",
    "char-106": "DaxMateB",
    "scene-001-s01": "Gate",
    "scene-002-s01": "GasStation",
    "scene-003-s01": "Scrap",
    "scene-004-s01": "ShopNight",
    "scene-004-s02": "ShopDawn",
    "scene-004-s03": "ShopDay",
    "scene-004-s04": "ShopDusk",
    "scene-005-s01": "DirtRoad",
    "scene-006-s01": "CampScrap",
    "char-002-w02": "SloaneWhite",
    "char-006": "Nora",
    "char-007": "Bruno",
    "char-008": "Pip",
    "char-009": "Wade",
    "char-010": "Walt",
    "char-011": "Rosa",
    "char-107": "GuardA",
    "char-108": "GuardB",
    "prop-001": "Vending",
    "prop-002": "Water",
}


def unpack_zip(zip_path: Path) -> Path:
    dest = Path("/tmp") / zip_path.stem
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.unpack_archive(str(zip_path), str(dest))
    if (dest / "package-manifest.json").is_file():
        return dest
    hits = list(dest.rglob("package-manifest.json"))
    if not hits:
        raise SystemExit("no package-manifest.json")
    return hits[0].parent


def extract_h3(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    for i, line in enumerate(lines):
        if line.strip() == _H3:
            return "\n".join(lines[i:]).strip() + "\n"
    raise SystemExit("standalone 【H3 提示词】 line missing")


def parse_uploads(text: str, asset_ids: list[str]) -> list[tuple[str, str]]:
    """Manifest order. Names may contain （） before the asset id."""
    head = text.replace("\r\n", "\n").split("【H3 提示词】", 1)[0]
    out: list[tuple[str, str]] = []
    for aid in asset_ids:
        key = aid.lower()
        disp = _LABEL.get(key, aid)
        for line in head.splitlines():
            if key in line.lower() and line.strip()[:1].isdigit():
                disp = line.split("（", 1)[0].split(".", 1)[-1].strip() or disp
                break
        if key not in head.lower():
            raise SystemExit(f"{aid} missing from upload block")
        out.append((key, disp))
    return out


def write_unit(pack: Path, unit: dict, asset_index: dict) -> dict:
    uid = unit["unit_id"]
    dur = float(unit["duration_seconds"])
    raw = (pack / unit["prompt"]).read_text(encoding="utf-8")
    uploads = parse_uploads(raw, list(unit.get("asset_ids") or []))
    h3_src = extract_h3(raw)
    labeled = [(aid, _LABEL.get(aid, disp)) for aid, disp in uploads]
    h3, injected = ensure_bind_line(h3_src, labeled)
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
        expected_markers = {marker: 0 for marker in _LATENT}
    else:
        expected_markers = {marker: 1 for marker in _LATENT}
        # Chain tails omit the handoff section. Older packs have no start_mode
        # and still require all three sections.
        if start_mode == "parent_latent" and unit.get("expects_handoff") is False:
            expected_markers[relay] = 0
    for marker in _LATENT:
        count = h3_src.count(marker)
        if count != expected_markers[marker]:
            issues.append(f"{marker} count={count}")
    if EXPECTED_DURATION is not None and abs(dur - EXPECTED_DURATION) > 0.001:
        issues.append(f"duration {dur} != {EXPECTED_DURATION}")
    if "【镜头" in h3_src:
        issues.append("unexpected per-shot clocks in light pack")
    if _EN_DIALOGUE.findall(h3_src) != _EN_DIALOGUE.findall(h3):
        issues.append("english dialogue changed while binding")
    if [a for a, _ in uploads] != [a.lower() for a in unit.get("asset_ids") or []]:
        issues.append(
            f"upload order {[a for a,_ in uploads]} != manifest {unit.get('asset_ids')}"
        )

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

    job_name = f"{EPISODE}-{uid}"
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

    prefix = f"{FILE_HEAD}-{uid}-{FILE_TAG}"
    fields: dict[str, object] = {f"ref_image_{i}": p for i, p in enumerate(staged)}
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
    refs = {k: str(v) for k, v in fields.items() if k.startswith("ref_")}
    w_viol = list(audit_pack_prompt_wiring(h3, wired, refs))
    s_viol, s_warn = audit_pack_prompt_semantics(wired, refs)
    if _body_for_audit(h3) != _body_for_audit(wired):
        w_viol.append("WIRE_CHANGED_BODY")
    at_tokens = sorted({f"{a}-{b}".lower() for a, b in _AT.findall(h3)})
    unbound = []
    for tok in at_tokens:
        if not any(aid == tok for aid, _ in staged_meta):
            unbound.append(tok)
    missing_pic = [i for i in range(1, len(staged) + 1) if f"<Picture {i}>" not in wired]
    if missing_pic:
        issues.append(f"unwired pictures {missing_pic}")
    if len(staged) > 9:
        issues.append(f"too many refs {len(staged)}")
    if "湿" in h3_src and any(a == "char-001" for a, _ in staged_meta):
        warnings.append("Ava sheet is dry; wet-clothes lines stay as written")

    (job / "job.yaml").write_text(
        yaml.safe_dump(
            {
                "template": "yz_h3_ep_unit",
                "episode": EPISODE,
                "unit_id": uid,
                "pack_kind": PACK_KIND,
                "parent_unit_id": unit.get("parent_unit_id"),
                "start_mode": unit.get("start_mode"),
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
    dialogues = _EN_DIALOGUE.findall(h3_src)
    audit = {
        "unit": uid,
        "job": job_name,
        "duration_seconds": dur,
        "parent_unit_id": unit.get("parent_unit_id"),
        "upload_ids": [a for a, _ in uploads],
        "staged": [{"picture": i + 1, "asset_id": a, "source": r} for i, (a, r) in enumerate(staged_meta)],
        "bind_line_injected": injected,
        "body_diff_beyond_bind": body_diff,
        "dialogues": dialogues,
        "issues": issues,
        "asset_warnings": warnings,
        "unbound_at_tokens": unbound,
        "wiring_violations": w_viol,
        "semantic_violations": s_viol,
        "semantic_warnings": s_warn,
        "preflight_ok": pf["ok"],
        "light_pack": True,
        "notime_stripped": False,
    }
    (assets_dir / "prompt_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    hard = (not pf["ok"]) or issues or s_viol or w_viol or unbound or body_diff
    flag = "FAIL" if hard else ("WARN" if warnings or s_warn else "OK")
    print(
        f"{flag} {job_name} dur={dur}s parent={unit.get('parent_unit_id')} "
        f"refs={len(staged)} inject={injected}"
    )
    print("  " + " ".join(f"P{i+1}={a}" for i, (a, _) in enumerate(staged_meta)))
    for item in issues + unbound + w_viol + s_viol:
        print("  ISSUE", item)
    for w in warnings:
        print("  ADAPT", w)
    return audit


def main() -> int:
    pack = unpack_zip(ZIP)
    man = json.loads((pack / "package-manifest.json").read_text(encoding="utf-8"))
    asset_index = {a["asset_id"].lower(): a for a in man["assets"]}
    print("=== PACK ===")
    print(man.get("package"), man.get("title"))
    rows = [write_unit(pack, unit, asset_index) for unit in man["units"]]
    report = Path("runs/ep01_dead_v1_unpack_audit.json")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps({"units": rows, "kept_as_packed": True}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ok_n = sum(
        1
        for r in rows
        if r["preflight_ok"]
        and not r["issues"]
        and not r["wiring_violations"]
        and not r["semantic_violations"]
        and not r["unbound_at_tokens"]
        and not r["body_diff_beyond_bind"]
    )
    print(f"\nreport {report} clean={ok_n}/{len(rows)}")
    proc = subprocess.run(
        [sys.executable, "scripts/audit_pack_prompts.py", "--glob", f"{EPISODE}-U*"],
        capture_output=True,
        text=True,
    )
    print("=== formal audit exit", proc.returncode, "===")
    for ln in (proc.stdout + proc.stderr).splitlines():
        if any(x in ln for x in ("PASS", "FAIL", "WARN", "units", "OK")):
            print(ln)
    return 0 if ok_n == len(rows) and proc.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
