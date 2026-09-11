#!/usr/bin/env python3
"""Convert EP upload / H3 latent packs into comfy-orch job directories."""

from __future__ import annotations

import argparse
from pathlib import Path

from comfy_orch.ep_pack import build_pack_jobs, list_unit_ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "packs",
        nargs="+",
        type=Path,
        help="Pack roots: EP03/EP04 (upload-manifest.json) or EP01 H3 latent (images/+prompts/)",
    )
    parser.add_argument(
        "-o",
        "--out",
        type=Path,
        default=Path("jobs/ep_units"),
        help="Output root for job directories (default: jobs/ep_units)",
    )
    parser.add_argument(
        "--unit",
        action="append",
        dest="units",
        help="Only convert these unit ids (repeatable). Default: all units.",
    )
    args = parser.parse_args()

    written: list[Path] = []
    for pack in args.packs:
        pack = pack.resolve()
        units = args.units
        if units is None:
            print(f"{pack.name}: units={','.join(list_unit_ids(pack))}")
        jobs = build_pack_jobs(pack, args.out.resolve(), unit_ids=units)
        written.extend(jobs)
        for job in jobs:
            print(f"wrote {job}")

    print(f"done: {len(written)} job(s) -> {args.out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
