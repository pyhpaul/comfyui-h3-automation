#!/usr/bin/env python3
"""Verify project-owned public assets, optionally including local-only source media."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def project_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError(f"asset path escapes project: {relative}")
    return path


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def verify_assets(root: Path, manifest: dict, include_local: bool = False) -> dict:
    if manifest.get("schema") != "episode-post-assets/v1":
        raise ValueError("unsupported project asset manifest")
    checked = []
    for item in manifest["assets"]:
        if item["visibility"] not in ("public", "local"):
            raise ValueError("unsupported asset visibility")
        if item["visibility"] == "local" and not include_local:
            continue
        path = project_path(root, item["path"])
        if digest(path) != item["sha256"]:
            raise ValueError(f"asset hash mismatch: {item['id']}")
        if "bytes" in item and path.stat().st_size != item["bytes"]:
            raise ValueError(f"asset size mismatch: {item['id']}")
        for field in ("credits", "review"):
            if field in item and not project_path(root, item[field]).is_file():
                raise ValueError(f"missing asset {field}: {item['id']}")
        checked.append(item["id"])
    return {"passed": True, "checked": checked, "include_local": include_local}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--include-local", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((args.root / "assets/episode_post/manifest.json").read_text())
    print(json.dumps(verify_assets(args.root, manifest, args.include_local)))


if __name__ == "__main__":
    main()
