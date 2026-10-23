#!/usr/bin/env python3
"""Unpack 离婚后，我成了前夫的继母 EP01-EP71 H3 manual-call v21 (20261020).

Usage: unpack_lihun_jimu_v21.py [EP01 [EP02 ...]]   (default: all 71)
Does not queue. Per-episode package dirs are -v2 except EP57/59/60/67/
68/70/71 (-v3); each is located by glob. Reports land in runs/.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP = next((ROOT / ".cache/lihun_jimu_v21/extracted").glob("*EP01-EP71*"))


def load_mod():
    path = ROOT / "scripts" / "unpack_ep01_dead_v1.py"
    spec = importlib.util.spec_from_file_location("unpack_ep01_dead_v1", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._LABEL.clear()
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
    mod.FILE_TAG = "lihun"
    wanted = [a.upper() for a in sys.argv[1:]] or [f"EP{e:02d}" for e in range(1, 72)]
    failed = 0
    for head in wanted:
        packs = sorted(TOP.glob(f"{head}-H3-manual-call-package-v*"))
        if len(packs) != 1:
            print(f"{head}: package dirs {packs}"); failed += 1; continue
        pack = packs[0]
        man = json.loads((pack / "package-manifest.json").read_text(encoding="utf-8"))
        mod.EPISODE = f"{head}-继母-v21"
        mod.PACK_KIND = f"{head.lower()}_lihun_v21"
        mod.FILE_HEAD = head
        asset_index = {a["asset_id"].lower(): a for a in man["assets"]}
        units = man["units"]
        prepared = []
        for index, unit in enumerate(units):
            row = dict(unit)
            nxt = units[index + 1]["start_mode"] if index + 1 < len(units) else None
            if row.get("start_mode") == "parent_latent":
                row["expects_handoff"] = nxt == "parent_latent"
            prepared.append(row)
        rows = [mod.write_unit(pack, unit, asset_index) for unit in prepared]
        report = ROOT / "runs" / f"{head.lower()}_lihun_v21_unpack_audit.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            json.dumps({"units": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        ok_n = clean(rows)
        print(f"{head} units={len(rows)} clean={ok_n}/{len(rows)} report={report.name}")
        if ok_n != len(rows):
            failed += 1
            for row in rows:
                if not (
                    row["preflight_ok"]
                    and not row["issues"]
                    and not row["wiring_violations"]
                    and not row["semantic_violations"]
                    and not row["unbound_at_tokens"]
                    and not row["body_diff_beyond_bind"]
                ):
                    print(
                        " ",
                        row["unit"],
                        row["issues"],
                        row["wiring_violations"],
                        row["semantic_violations"],
                        row["unbound_at_tokens"],
                        "preflight",
                        row["preflight_ok"],
                        "body",
                        row["body_diff_beyond_bind"],
                    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
