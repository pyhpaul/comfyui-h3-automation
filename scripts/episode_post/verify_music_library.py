#!/usr/bin/env python3
"""Verify local catalog identity/evidence; optional independent full audio decoding."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def verify_identity(root: Path, record: dict) -> Path:
    path = (root / record["path"]).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("catalog path escapes project")
    if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
        raise ValueError(f"asset hash mismatch: {record['path']}")
    if path.stat().st_size != record["bytes"]:
        raise ValueError(f"asset size mismatch: {record['path']}")
    return path


def verify_catalog(root: Path, catalog: dict, decode: bool = False) -> dict:
    if catalog["schema"] != "episode-music-catalog/v1" or not catalog["tracks"]:
        raise ValueError("unsupported or empty catalog")
    verify_identity(root, catalog["selection"])
    for selection in catalog.get("additional_selections", []):
        verify_identity(root, selection)
    ids, hashes = set(), set()
    for track in catalog["tracks"]:
        if track["id"] in ids or track["sha256"] in hashes:
            raise ValueError("duplicate track ID or audio bytes")
        ids.add(track["id"])
        hashes.add(track["sha256"])
        if track["license"]["id"] != "CC-BY-4.0" or not track["attribution"] or not track["evidence"]:
            raise ValueError("missing reviewed licensing evidence or attribution")
        path = verify_identity(root, track)
        for evidence in track["evidence"]:
            verify_identity(root, evidence)
        duration = track["technical"]["duration_s"]
        for segment in track["candidate_segments"]:
            if not 0 <= segment["start"] < segment["end"] <= duration:
                raise ValueError("candidate segment exceeds source duration")
        if decode:
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
                            "-vn", "-f", "null", "-"], check=True)
    return {"tracks": len(ids), "total_bytes": sum(t["bytes"] for t in catalog["tracks"]),
            "full_decode_rechecked": decode, "realtime_listening": "NOT_DONE"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--decode", action="store_true")
    args = parser.parse_args()
    catalog = json.loads((args.root / "assets/episode_post/music/catalog.json").read_text())
    print(json.dumps(verify_catalog(args.root, catalog, args.decode)))


if __name__ == "__main__":
    main()
