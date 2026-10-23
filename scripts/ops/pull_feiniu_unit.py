#!/usr/bin/env python3
"""Download one Feiniu archive unit (mp4 + siblings) to a local directory.

Prep helper for FaceRefine A/B — does not touch GPU.

Usage:
  PYTHONPATH=src python scripts/ops/pull_feiniu_unit.py \\
    --batch '文武双全TEST-黑手党EP01（10.19）' \\
    --episode EP01 --unit U01 \\
    --out jobs/facerefine_test/source_U01
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from comfy_orch.feiniu_archive import (  # noqa: E402
    PASSFILE,
    SHARE,
    connect_feiniu,
    remote_unit_dir,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True)
    ap.add_argument("--episode", required=True)
    ap.add_argument("--unit", required=True)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    remote = remote_unit_dir(args.batch, args.episode, args.unit)
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    smb = connect_feiniu(PASSFILE)
    try:
        items = smb.listPath(SHARE, remote + "\\*")
        names = [
            it.get_longname()
            for it in items
            if it.get_longname() not in {".", ".."} and not it.is_directory()
        ]
        if not names:
            raise SystemExit(f"empty or missing: {remote}")
        print(f"REMOTE {remote} files={names}", flush=True)
        for name in names:
            buf = io.BytesIO()
            smb.getFile(SHARE, remote + "\\" + name, buf.write)
            path = out / name
            path.write_bytes(buf.getvalue())
            print(f"GOT {name} bytes={path.stat().st_size}", flush=True)
    finally:
        smb.close()

    mp4s = list(out.glob("*.mp4"))
    if not mp4s:
        raise SystemExit(f"no mp4 under {out}")
    print(f"READY mp4={mp4s[0]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
