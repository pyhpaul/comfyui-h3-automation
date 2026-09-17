#!/usr/bin/env python3
"""Refresh 绑定资产 drama labels on existing manual-call jobs (engineering only).

Reads ``prompt_pack_full.txt`` upload order for display names, rewrites the
bind line + rewires ``prompt_h3.txt`` / ``job.yaml`` prompt field, updates
``prompt_audit.json`` engineering flags. Does not change shot prose.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from comfy_orch.named_assets_bind import ensure_bind_line, refresh_bind_line_labels
from comfy_orch.paths import project_root
from comfy_orch.prompt_wire import wire_pack_prompt

_ASSET_IN_LINE = re.compile(
    r"^(\d+)\.\s*([^（(]+)[（(]((?:char|prop|scene)-\d+[A-Za-z0-9._-]*)\s*[｜|]",
    re.I,
)
_H3 = "【H3 提示词】"


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
    return out


def extract_h3(text: str) -> str:
    if _H3 not in text:
        raise ValueError("missing H3 section")
    return f"{_H3}\n{text.split(_H3, 1)[1].strip()}\n"


def refresh_job(job_dir: Path) -> dict:
    assets = job_dir / "assets"
    full = (assets / "prompt_pack_full.txt").read_text(encoding="utf-8")
    entries = parse_upload_entries(full)
    raw_job = yaml.safe_load((job_dir / "job.yaml").read_text(encoding="utf-8"))
    fields = dict(raw_job.get("fields") or {})
    refs = {k: v for k, v in fields.items() if k.startswith("ref_image_")}

    src_path = assets / "prompt_source.txt"
    if src_path.is_file():
        h3 = src_path.read_text(encoding="utf-8")
    else:
        h3 = extract_h3(full)

    before = h3
    if "绑定资产：" in h3 and entries:
        h3 = refresh_bind_line_labels(h3, entries)
        injected = False
        refreshed = h3 != before
    else:
        h3, injected = ensure_bind_line(h3, entries)
        refreshed = injected

    wired = wire_pack_prompt(h3, refs)
    fields["prompt"] = wired
    raw_job["fields"] = fields
    (job_dir / "job.yaml").write_text(
        yaml.safe_dump(raw_job, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    src_path.write_text(h3, encoding="utf-8")
    (assets / "prompt_h3.txt").write_text(wired, encoding="utf-8")

    audit_path = assets / "prompt_audit.json"
    audit: dict = {}
    if audit_path.is_file():
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["bind_line_injected"] = bool(audit.get("bind_line_injected")) or injected
    audit["bind_labels_refreshed"] = refreshed
    audit["upload_ids"] = [a for a, _ in entries]
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "job": job_dir.name,
        "refreshed": refreshed,
        "injected": injected,
        "bind_preview": next((ln for ln in h3.splitlines() if ln.startswith("绑定资产：")), ""),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--glob", required=True, help="Glob under jobs/ep_units")
    args = ap.parse_args()
    root = project_root()
    jobs = sorted((root / "jobs" / "ep_units").glob(args.glob))
    if not jobs:
        print("no jobs", file=sys.stderr)
        return 2
    for job in jobs:
        try:
            info = refresh_job(job)
        except Exception as e:
            print(f"FAIL {job.name}: {e}", flush=True)
            continue
        print(
            f"{'REFRESH' if info['refreshed'] or info['injected'] else 'OK'} "
            f"{info['job']} {info['bind_preview'][:120]}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
