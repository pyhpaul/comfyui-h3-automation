#!/usr/bin/env python3
"""Unpack + audit EP01《戴戒进厅》H3 manual-call v3.

Keeps shot clocks and latent overlap tails. Does not queue.
Resolves assets from package-manifest paths, never Windows paths.
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

ZIP = Path("/mnt/c/Users/lxy/Downloads/EP01-戴戒进厅-H3-manual-call-package-v3.zip")
OUT = Path("jobs/ep_units")
EPISODE = "EP01-戴戒进厅-v3"
PACK_KIND = "ep01_manual_v3_daijie"
_H3 = "【H3 提示词】"
_EN_DIALOGUE = re.compile(r"[（(]([A-Za-z][^）)]*\s[^）)]+)[）)]")
_AT = re.compile(
    r"@(char|prop|scene)-([A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*)",
    re.I,
)
_ASSET_IN_LINE = re.compile(
    r"^(\d+)\.\s*([^（(]+)[（(]((?:char|prop|scene)-\d+[A-Za-z0-9._-]*)\s*[｜|]",
    re.I,
)
_SHOT = re.compile(
    r"【镜头(\d+)｜\s*(\d+(?:\.\d+)?)\s*(?:--|–|—|-)\s*(\d+(?:\.\d+)?)\s*秒"
)
_LATENT = (
    "【H3 latent 接入文字】",
    "【交出状态】",
    "【H3 latent 接力文字】",
)

# Short drama labels so bind lines do not steal English names from dialogue.
_LABEL = {
    "char-001": "Sean",
    "char-002": "Royce",
    "char-003": "FlagWoman",
    "char-004": "Sabu",
    "char-005": "Claire",
    "char-006": "Riva",
    "char-007": "Grant",
    "scene-001": "雨夜码头",
    "scene-002": "洛克舞厅",
    "prop-001": "薄戒",
    "prop-002": "戒指盒",
    "prop-003": "会客卡",
    "prop-004": "短棍",
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


def parse_uploads(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for line in text.replace("\r\n", "\n").splitlines():
        if line.startswith("【H3 提示词】"):
            break
        if any(k in line for k in ("纯文字", "无图片", "不上传", "不绑定")):
            continue
        m = _ASSET_IN_LINE.match(line.strip())
        if m:
            out.append((m.group(3).lower(), m.group(2).strip()))
    return out


def shot_issues(h3: str, duration: float) -> list[str]:
    shots = [(int(a), float(b), float(c)) for a, b, c in _SHOT.findall(h3)]
    issues: list[str] = []
    if not shots:
        return ["no shot clocks"]
    if [n for n, _, _ in shots] != list(range(1, len(shots) + 1)):
        issues.append(f"shot numbers {[n for n, _, _ in shots]}")
    if abs(shots[0][1]) > 0.001:
        issues.append(f"first shot starts at {shots[0][1]}")
    for prev, nxt in zip(shots, shots[1:]):
        if abs(prev[2] - nxt[1]) > 0.001:
            issues.append(f"shot gap {prev[0]}->{nxt[0]}")
    if abs(shots[-1][2] - duration) > 0.05:
        issues.append(f"last shot end {shots[-1][2]} != duration {duration}")
    return issues


def write_unit(pack: Path, unit: dict, asset_index: dict) -> dict:
    uid = unit["unit_id"]
    dur = float(unit["duration_seconds"])
    raw = (pack / unit["prompt"]).read_text(encoding="utf-8")
    uploads = parse_uploads(raw)
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
    for marker in _LATENT:
        if h3_src.count(marker) != 1:
            issues.append(f"{marker} count={h3_src.count(marker)}")
    issues.extend(shot_issues(h3_src, dur))
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

    prefix = f"EP01-{uid}-v3"
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
        if not any(
            aid == tok or aid.startswith(tok + "-") or tok.startswith(aid + "-")
            for aid, _ in staged_meta
        ):
            unbound.append(tok)
    missing_pic = [i for i in range(1, len(staged) + 1) if f"<Picture {i}>" not in wired]
    if missing_pic:
        issues.append(f"unwired pictures {missing_pic}")
    if len(staged) > 8:
        issues.append(f"too many refs {len(staged)}")

    # Dock wet-state is prose-only while Sean sheet is dry.
    if uid in {"U01", "U02", "U03", "U04", "U05", "U06"} and "湿" in h3_src:
        warnings.append("Sean sheet is dry clothing; dock wet/blood states are text-only")

    (job / "job.yaml").write_text(
        yaml.safe_dump(
            {
                "template": "yz_h3_ep_unit",
                "episode": EPISODE,
                "unit_id": uid,
                "pack_kind": PACK_KIND,
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
        "shot_count": len(_SHOT.findall(h3_src)),
        "issues": issues,
        "asset_warnings": warnings,
        "unbound_at_tokens": unbound,
        "wiring_violations": w_viol,
        "semantic_violations": s_viol,
        "semantic_warnings": s_warn,
        "preflight_ok": pf["ok"],
        "reordered": False,
        "notime_stripped": False,
    }
    (assets_dir / "prompt_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    hard = (not pf["ok"]) or issues or s_viol or w_viol or unbound or body_diff
    flag = "FAIL" if hard else ("WARN" if warnings or s_warn else "OK")
    print(
        f"{flag} {job_name} dur={dur}s parent={unit.get('parent_unit_id')} "
        f"shots={audit['shot_count']} refs={len(staged)} inject={injected}"
    )
    print("  " + " ".join(f"P{i+1}={a}" for i, (a, _) in enumerate(staged_meta)))
    if dialogues:
        print("  dialogue:", " | ".join(dialogues))
    for item in issues + unbound + w_viol + s_viol:
        print("  ISSUE", item)
    for w in warnings:
        print("  ADAPT", w)
    for w in s_warn:
        print("  SEM-WARN", str(w)[:160])
    return audit


def main() -> int:
    pack = unpack_zip(ZIP)
    man = json.loads((pack / "package-manifest.json").read_text(encoding="utf-8"))
    asset_index = {a["asset_id"].lower(): a for a in man["assets"]}
    print("=== PACK ===")
    print(man.get("package"))
    print("state", man.get("package_state"))
    print("upload_auth", man.get("actual_upload_authorized"), "submit_auth", man.get("actual_submission_authorized"))
    print("format", man.get("format_profile"), man.get("quality_rule_profile"))
    rows = [write_unit(pack, unit, asset_index) for unit in man["units"]]
    report = Path("runs/ep01_daijie_v3_unpack_audit.json")
    report.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "units": rows,
        "not_queued": True,
        "notime_stripped": False,
        "image_notes": [
            "Sean: dark grey crew shirt, black pants, dark wavy hair — distinct.",
            "Royce: navy double-breasted blazer, white open shirt, older salt-pepper — distinct from Sean.",
            "Flag woman: navy cropped zip jacket, black trousers, boots — distinct silhouette.",
            "Sabu: olive hooded jacket, combat boots — distinct from wedding Claire.",
            "Claire: white strapless wedding dress + veil — unique silhouette.",
            "Riva: muted mauve suit skirt — distinct from Claire and Flag woman.",
            "Grant: black tuxedo jacket, burgundy trousers — distinct from Royce navy blazer.",
            "Dock wet shirt / finger blood crust are prose-only vs dry character sheets.",
        ],
        "dialogue_note": (
            "Script has 21 ASCII-quoted fragments; H3 packs 20 （） blocks. "
            "U01 merges Kill him now. + He came on his own feet. Put him down. "
            "to match screenshot mapping."
        ),
    }
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
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
