#!/usr/bin/env python3
"""Unpack 潮缚 EP24/EP62/EP63 manual-call packs into v2 (redo) jobs.

EP24: whole-episode redo (scene must match EP23-U04 film, true night).
EP62/EP63: first full render in this repo. Wenxi chain only.
Does not queue. Scene four-grid crops / night locks are applied afterwards
by editing each job's assets (see docs/ops/2026-10-21 fix standard).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKS = ROOT / ".cache" / "chaofu_redo_packs"
EPISODES = ["EP24", "EP62", "EP63"]


def load_mod():
    path = ROOT / "scripts" / "unpack_ep01_dead_v1.py"
    spec = importlib.util.spec_from_file_location("unpack_ep01_dead_v1", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def clean(rows: list[dict]) -> int:
    return sum(
        1 for r in rows
        if r["preflight_ok"] and not r["issues"]
        and not r["wiring_violations"] and not r["semantic_violations"]
        and not r["unbound_at_tokens"] and not r["body_diff_beyond_bind"]
    )


def main() -> int:
    mod = load_mod()
    mod._LABEL = {}  # display names must come from this pack's upload blocks
    failed = 0
    for ep in EPISODES:
        pack = PACKS / f"{ep}-H3-manual-call-package-v1"
        man = json.loads((pack / "package-manifest.json").read_text(encoding="utf-8"))
        mod.EPISODE = f"{ep}-潮缚-v2"
        mod.PACK_KIND = f"chaofu_{ep.lower()}_v2"
        mod.FILE_HEAD = ep
        mod.FILE_TAG = "chaofu"
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
        report = ROOT / "runs" / f"chaofu_{ep.lower()}_v2_unpack_audit.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({"units": rows}, ensure_ascii=False, indent=2),
                          encoding="utf-8")
        ok_n = clean(rows)
        print(f"{ep}: clean={ok_n}/{len(rows)} report={report.name}")
        if ok_n != len(rows):
            failed += 1
            for row in rows:
                bad = (not row["preflight_ok"] or row["issues"]
                       or row["wiring_violations"] or row["semantic_violations"]
                       or row["unbound_at_tokens"] or row["body_diff_beyond_bind"])
                if bad:
                    print(f"  {row['unit']}: issues={row['issues']} "
                          f"wiring={row['wiring_violations']} "
                          f"semantic={row['semantic_violations']} "
                          f"unbound={row['unbound_at_tokens']} "
                          f"body_diff={row['body_diff_beyond_bind']} "
                          f"preflight={row['preflight_ok']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
