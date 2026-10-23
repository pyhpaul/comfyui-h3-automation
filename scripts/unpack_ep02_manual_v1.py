#!/usr/bin/env python3
"""Unpack + audit EP02《改口要代价》H3 manual-call v1.

Keeps shot clocks. Does not queue.
Uses package-manifest asset_ids as the upload order (TXT lines may bundle
multiple ids/paths). Independent reanchors (U01/U03/U05/U07) keep parent=None.
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

ZIP = Path("/mnt/c/Users/lxy/Downloads/EP02-改口要代价-H3-manual-call-package-v1.zip")
OUT = Path("jobs/ep_units")
EPISODE = "EP02-改口要代价-v1"
PACK_KIND = "ep02_manual_v1_gai kou"
_H3 = "【H3 提示词】"
_EN_DIALOGUE = re.compile(r"[（(]([A-Za-z][^）)]*\s[^）)]+)[）)]")
_AT = re.compile(
    r"@(char|prop|scene)-([A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*)",
    re.I,
)
_ANY_AID = re.compile(r"(?:char|prop|scene)-\d+[A-Za-z0-9._-]*", re.I)
_SHOT = re.compile(
    r"【镜头(\d+)｜\s*(\d+(?:\.\d+)?)\s*(?:--|–|—|-)\s*(\d+(?:\.\d+)?)\s*秒"
)
_LATENT = (
    "【H3 latent 接入文字】",
    "【交出状态】",
    "【H3 latent 接力文字】",
)
_LABEL = {
    "char-001": "Sean",
    "char-001-f01": "SeanFlash",
    "char-005": "Claire",
    "char-005-f02": "ClaireFlash",
    "char-006": "Riva",
    "char-007": "Grant",
    "char-007-f03": "GrantFlash",
    "char-008": "Guest",
    "scene-002": "宴会厅",
    "scene-003": "汽车旅馆",
    "scene-004": "出租屋",
    "prop-001": "薄戒",
    "prop-005": "酒杯",
    "prop-006": "LOCKE卡",
    "prop-007": "台灯",
    "prop-008": "门链",
}
_REANCHOR = {"U01", "U03", "U05", "U07"}


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


def ids_mentioned_in_upload_block(text: str) -> set[str]:
    head = text.split(_H3, 1)[0]
    start = head.find("【上传资产路径与顺序】")
    block = head[start:] if start >= 0 else head
    return {m.group(0).lower() for m in _ANY_AID.finditer(block)}


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
    parent = unit.get("parent_unit_id")
    raw = (pack / unit["prompt"]).read_text(encoding="utf-8")
    h3_src = extract_h3(raw)
    upload_ids = [a.lower() for a in unit["asset_ids"]]
    mentioned = ids_mentioned_in_upload_block(raw)
    labeled = [(aid, _LABEL.get(aid, aid)) for aid in upload_ids]
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
    missing_mention = [a for a in upload_ids if a not in mentioned]
    if missing_mention:
        issues.append(f"upload block missing ids {missing_mention}")
    if uid in _REANCHOR and parent is not None:
        issues.append(f"reanchor unit has parent {parent}")
    if uid not in _REANCHOR and not parent:
        warnings.append("non-reanchor unit has no parent_unit_id")

    staged_meta: list[tuple[str, str]] = []
    for aid in upload_ids:
        hit = asset_index.get(aid)
        if not hit:
            issues.append(f"missing asset id {aid}")
            continue
        rel = str(hit.get("path") or "")
        if not (pack / rel).is_file():
            issues.append(f"missing file {rel}")
            continue
        staged_meta.append((aid, rel))

    # Same-person current vs flashback must not co-bind.
    stems = {a.split("-f")[0] if "-f" in a else a for a, _ in staged_meta if a.startswith("char-")}
    flash = [a for a, _ in staged_meta if "-f" in a]
    current = [a for a, _ in staged_meta if a.startswith("char-") and "-f" not in a]
    for f in flash:
        base = f.split("-f")[0]
        if any(c == base for c in current):
            issues.append(f"current+flash co-bound for {base}")

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

    if len(staged) > 8:
        issues.append(f"too many refs {len(staged)}")

    prefix = f"EP02-{uid}-v1"
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

    if "红" in h3_src and "颧" in h3_src:
        warnings.append("Sean cheek red mark is text-only on a clean face sheet")
    if uid in {"U03", "U04"}:
        warnings.append("motel flashback: adult fully-clothed conflict; needs human review after render")

    (job / "job.yaml").write_text(
        yaml.safe_dump(
            {
                "template": "yz_h3_ep_unit",
                "episode": EPISODE,
                "unit_id": uid,
                "pack_kind": PACK_KIND,
                "parent_unit_id": parent,
                "independent_reanchor": uid in _REANCHOR,
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
        "parent_unit_id": parent,
        "independent_reanchor": uid in _REANCHOR,
        "upload_ids": upload_ids,
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
        f"{flag} {job_name} dur={dur}s parent={parent} reanchor={uid in _REANCHOR} "
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
    print("profile", man.get("profile_id"), man.get("format_profile"))
    rows = [write_unit(pack, unit, asset_index) for unit in man["units"]]
    report = Path("runs/ep02_gaikou_v1_unpack_audit.json")
    report.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "units": rows,
        "not_queued": True,
        "notime_stripped": False,
        "queue_plan": [
            "U01-U02 banquet chain (U01 reanchor)",
            "U03-U04 motel flashback chain (U03 reanchor)",
            "U05-U06 apartment flashback chain (U05 reanchor)",
            "U07-U10 banquet return chain (U07 reanchor)",
        ],
        "continuity_note": (
            "Pack text says Higgsfield video_references; our Comfy runner uses "
            "motion_latent within each scene chain. Reanchor units start with no parent."
        ),
        "image_notes": [
            "Sean current formal vs F01 charcoal Henley/jeans/brown boots — distinct.",
            "Claire wedding dress vs F02 mist-blue mandarin blouse + charcoal pants — distinct.",
            "Grant tuxedo vs F03 burgundy shirt black pants — distinct silhouette.",
            "Guest navy suit with tie — distinct from Grant peak-lapel no-tie.",
            "Never co-bind current + flash variants of the same person.",
            "Sean cheek red mark is prose-only.",
        ],
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
