#!/usr/bin/env python3
"""Unpack 寿命掮客 EP01-EP06 H3 manual-call v1 (20261021). Does not queue.

Per-unit durations (duration_policy=per_unit_content_v1), so the fixed
15.083s light-pack duration check in write_unit is disabled.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP = ROOT / ".cache/shouming_ep01_06_20261021"


def load_mod():
    path = ROOT / "scripts" / "unpack_ep01_dead_v1.py"
    spec = importlib.util.spec_from_file_location("unpack_ep01_dead_v1", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._LABEL.clear()
    mod.EXPECTED_DURATION = None
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
    mod.FILE_TAG = "shouming"
    wanted = [a.upper() for a in sys.argv[1:]] or [f"EP{e:02d}" for e in range(1, 7)]
    failed = 0
    for head in wanted:
        pack = TOP / f"{head}-H3-manual-call-package-v1"
        man = json.loads((pack / "package-manifest.json").read_text(encoding="utf-8"))
        mod.EPISODE = f"{head}-寿命掮客-v1"
        mod.PACK_KIND = f"{head.lower()}_shouming_v1"
        mod.FILE_HEAD = head
        asset_index = {a["asset_id"].lower(): a for a in man["assets"]}
        print("=== PACK ===", man.get("package"), man.get("title"), "units", len(man["units"]))
        units = man["units"]
        prepared = []
        for index, unit in enumerate(units):
            row = dict(unit)
            nxt = units[index + 1]["start_mode"] if index + 1 < len(units) else None
            if row.get("start_mode") == "parent_latent":
                row["expects_handoff"] = nxt == "parent_latent"
            prepared.append(row)
        rows = [mod.write_unit(pack, unit, asset_index) for unit in prepared]
        report = ROOT / "runs" / f"{head.lower()}_shouming_v1_unpack_audit.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            json.dumps({"units": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        ok_n = clean(rows)
        print(f"report {report.name} clean={ok_n}/{len(rows)}")
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
