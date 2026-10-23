#!/usr/bin/env python3
"""Unpack EP01–EP03《死人回来了》H3 light manual-call v2. Does not queue."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = Path("/mnt/c/Users/lxy/Documents/xwechat_files/wxid_7567265672712_c9a5/msg/file/2026-09")
PACKS = [
    {
        "zip": SRC / "EP01-H3-manual-call-package-v2(1).zip",
        "episode": "EP01-死人回来了-v2",
        "pack_kind": "ep01_dead_v2",
        "file_head": "EP01",
        "report": "runs/ep01_dead_v2_unpack_audit.json",
    },
    {
        "zip": SRC / "EP02-H3-manual-call-package-v2.zip",
        "episode": "EP02-不该存在的小店-v2",
        "pack_kind": "ep02_dead_v2",
        "file_head": "EP02",
        "report": "runs/ep02_dead_v2_unpack_audit.json",
    },
    {
        "zip": SRC / "EP03-H3-manual-call-package-v2.zip",
        "episode": "EP03-抢Vance钱-v2",
        "pack_kind": "ep03_dead_v2",
        "file_head": "EP03",
        "report": "runs/ep03_dead_v2_unpack_audit.json",
    },
]


def load_mod():
    path = ROOT / "scripts" / "unpack_ep01_dead_v1.py"
    spec = importlib.util.spec_from_file_location("unpack_ep01_dead_v1", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def clean(rows: list[dict]) -> int:
    return sum(
        1
        for r in rows
        if r["preflight_ok"]
        and not r["issues"]
        and not r["wiring_violations"]
        and not r["semantic_violations"]
        and not r["unbound_at_tokens"]
        and not r["body_diff_beyond_bind"]
    )


def main() -> int:
    mod = load_mod()
    mod.FILE_TAG = "deadv2"
    failed = 0
    for spec in PACKS:
        mod.EPISODE = spec["episode"]
        mod.PACK_KIND = spec["pack_kind"]
        mod.FILE_HEAD = spec["file_head"]
        pack = mod.unpack_zip(spec["zip"])
        man = json.loads((pack / "package-manifest.json").read_text(encoding="utf-8"))
        asset_index = {a["asset_id"].lower(): a for a in man["assets"]}
        print("=== PACK ===", man.get("package"), man.get("title"))
        rows = [mod.write_unit(pack, unit, asset_index) for unit in man["units"]]
        report = ROOT / spec["report"]
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            json.dumps({"units": rows, "kept_as_packed": True}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        ok_n = clean(rows)
        print(f"report {report.name} clean={ok_n}/{len(rows)}")
        if ok_n != len(rows):
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
