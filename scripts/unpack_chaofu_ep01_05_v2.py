#!/usr/bin/env python3
"""Unpack 潮缚 EP01-EP05 H3 manual-call v2 (20261020). Does not queue."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP = Path(
    "/tmp/chaofu_ep01-05_v2/extracted/"
    "潮缚-EP01-EP05-H3调用包-v2-20261020"
)


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
    mod.FILE_TAG = "chaofu"
    failed = 0
    for ep in range(1, 6):
        head = f"EP{ep:02d}"
        pack = TOP / f"{head}-H3-manual-call-package-v2"
        man = json.loads((pack / "package-manifest.json").read_text(encoding="utf-8"))
        mod.EPISODE = f"{head}-潮缚-v2"
        mod.PACK_KIND = f"ep{ep:02d}_chaofu_v2"
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
        report = ROOT / "runs" / f"ep{ep:02d}_chaofu_v2_unpack_audit.json"
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
