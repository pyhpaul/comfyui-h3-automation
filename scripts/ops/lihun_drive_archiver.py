#!/usr/bin/env python3
"""Standalone Drive->Feiniu archiver for lihun v23 Colab production.

Use when the batch host died but the guest phase keeps rendering in
the VM (it publishes every unit to Drive). Polls each manifest unit's
Drive receipt; on success pulls the unit files and archives the core
four to Feiniu. Idempotent: units already on Feiniu with same sizes
are skipped by archive_named_files. Runs until all units are archived
or failed, then exits.

  PYTHONPATH=src python scripts/ops/lihun_drive_archiver.py \
    --remote h3drive_h3:.../lihun-v23/<session> \
    --units-json .cache/lihun_v23_colab/input/units.json \
    --units-json .cache/lihun_v23_colab_ep06_10/input/units.json \
    --pull-dir .cache/colab_wenxi_setup/<session>/units
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from comfy_orch.feiniu_archive import archive_named_files  # noqa: E402

CONFIG = Path.home() / ".config/rclone-h3/rclone.conf"
FEINIU_BATCH = "离婚后（10.22）"


def remote_json(remote: str, tag: str):
    r = subprocess.run(
        ["rclone", "cat", f"{remote}/{tag}/phase.json",
         "--config", str(CONFIG)], capture_output=True, timeout=120)
    if r.returncode != 0:
        return None
    return json.loads(r.stdout)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--remote", required=True)
    ap.add_argument("--units-json", type=Path, action="append", required=True)
    ap.add_argument("--pull-dir", type=Path, required=True)
    ap.add_argument("--poll-s", type=int, default=45)
    args = ap.parse_args()

    units = []
    for p in args.units_json:
        units += json.loads(p.read_text())["units"]
    pending = {u["tag"]: u for u in units}
    failed = {}
    print(f"ARCHIVER_START units={len(pending)} remote={args.remote}",
          flush=True)
    while pending:
        for tag in list(pending):
            unit = pending[tag]
            try:
                receipt = remote_json(args.remote, tag)
            except Exception:
                receipt = None
            if not receipt:
                continue
            if receipt.get("state") == "failed":
                failed[tag] = str(receipt.get("error"))
                del pending[tag]
                print(f"UNIT_FAILED {tag} {failed[tag]}", flush=True)
                continue
            if receipt.get("state") != "success":
                continue
            dest = args.pull_dir / tag
            dest.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["rclone", "copy", f"{args.remote}/{tag}", str(dest),
                 "--config", str(CONFIG)], check=True, timeout=900)
            payloads = {}
            for name in (receipt["mp4_file"], receipt["latent_file"],
                         "prompt_h3.txt", "run_meta.json"):
                payloads[name] = (dest / name).read_bytes()
            remote_dir = archive_named_files(
                payloads, batch=FEINIU_BATCH, episode=unit["episode"],
                unit=f"{unit['unit']}-WENXI")
            del pending[tag]
            print(f"FEINIU {tag} -> {remote_dir}", flush=True)
        if pending:
            time.sleep(args.poll_s)
    print(f"ARCHIVER_DONE failed={failed}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
