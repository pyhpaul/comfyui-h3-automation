#!/usr/bin/env python3
"""Unpack 海外短剧测试2 EP01–EP03. Does not queue."""
from __future__ import annotations

import importlib.util
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZIP = Path("/mnt/c/Users/lxy/Downloads/海外短剧测试2-H3静态调用包-EP01至EP03-20260925.zip")
PACKS = [
    {
        "rel": "海外短剧测试2-H3静态调用包/ep01/deliverables/EP01-H3-manual-call-package-v1",
        "episode": "EP01-测试2-v1",
        "pack_kind": "test2_ep01_v1",
        "file_head": "EP01",
        "report": "runs/test2_ep01_unpack_audit.json",
    },
    {
        "rel": "海外短剧测试2-H3静态调用包/ep02/deliverables/EP02-H3-manual-call-package-v2",
        "episode": "EP02-测试2-v2",
        "pack_kind": "test2_ep02_v2",
        "file_head": "EP02",
        "report": "runs/test2_ep02_unpack_audit.json",
    },
    {
        "rel": "海外短剧测试2-H3静态调用包/ep03/deliverables/EP03-H3-manual-call-package-v1",
        "episode": "EP03-测试2-v1",
        "pack_kind": "test2_ep03_v1",
        "file_head": "EP03",
        "report": "runs/test2_ep03_unpack_audit.json",
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
    dest = Path("/tmp/h2-pack")
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir()
    with zipfile.ZipFile(ZIP) as zf:
        zf.extractall(dest)
    mod = load_mod()
    mod.FILE_TAG = "test2"
    failed = 0
    for spec in PACKS:
        mod.EPISODE = spec["episode"]
        mod.PACK_KIND = spec["pack_kind"]
        mod.FILE_HEAD = spec["file_head"]
        pack = dest / spec["rel"]
        man = json.loads((pack / "package-manifest.json").read_text(encoding="utf-8"))
        asset_index = {a["asset_id"].lower(): a for a in man["assets"]}
        print("=== PACK ===", man.get("package"), man.get("title"))
        rows = [mod.write_unit(pack, unit, asset_index) for unit in man["units"]]
        nines = [r["unit"] for r in rows if len(r["staged"]) == 9]
        missing9 = [
            r["unit"]
            for r in rows
            if len(r["staged"]) == 9 and "<Picture 9>" not in (pack and "")
        ]
        report = ROOT / spec["report"]
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            json.dumps({"units": rows, "nine_ref_units": nines}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        ok_n = clean(rows)
        print(f"report {report.name} clean={ok_n}/{len(rows)} nine={nines}")
        if ok_n != len(rows):
            failed += 1
        del missing9
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
