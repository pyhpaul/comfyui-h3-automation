#!/usr/bin/env python3
"""Preserve exact engine/skill/preset snapshots for a local agent edit comparison."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

from ep_pilot_timeline import verify_source


def copy_verified(source: Path, dest: Path, sha: str) -> None:
    verify_source(source, sha)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("xb") as handle:
        handle.write(source.read_bytes())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    root, out = args.root.resolve(), args.out.resolve()
    manifest = json.loads((out / "edit_manifest.json").read_text())
    shared = json.loads((out / "input_contract.json").read_text())
    for name, sha in manifest["engine_snapshot"].items():
        copy_verified(root / "scripts/episode_post" / name, out / "engine_snapshot" / name, sha)
    for item in shared["skill_snapshot"] + shared["available_presets"]:
        copy_verified(root / item["path"], out / "guidance_snapshot" / item["path"], item["sha256"])
    packages = {}
    for name in ("numpy", "faster-whisper", "pytest"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "NOT_INSTALLED"
    ffmpeg = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True).stdout.splitlines()[0]
    receipt = {"agent_id": manifest["agent_id"], "creative_author": manifest["creative_author"],
               "prior_exposure": manifest["prior_exposure"],
               "shared_input_sha256": hashlib.sha256((out / "input_contract.json").read_bytes()).hexdigest(),
               "creative_plan_sha256": hashlib.sha256((out / "creative_plan.json").read_bytes()).hexdigest(),
               "engine_snapshot": manifest["engine_snapshot"], "python": sys.version,
               "packages": packages, "ffmpeg": ffmpeg,
               "publication": "LOCAL_ONLY_NOT_UPLOADED",
               "comparison_limit": "Single known-history run, not a blinded or statistically controlled model evaluation"}
    with (out / "run_receipt.json").open("x") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"out": str(out), "snapshot_files": len(manifest["engine_snapshot"]) + len(shared["skill_snapshot"]) + len(shared["available_presets"])}))


if __name__ == "__main__":
    main()
