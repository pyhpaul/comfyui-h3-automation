#!/usr/bin/env python3
"""Append reviewed Incompetech candidates, preserving existing catalog rows and originals."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

from import_music_library import download, identity, inspect_asset, LICENSE
from verify_music_library import verify_catalog

BASE = "https://incompetech.com/music/royalty-free/"
HOSTS = frozenset({"incompetech.com"})


def build_entry(root: Path, choice: dict, metadata: dict, evidence: list[dict]) -> dict:
    isrc = metadata["isrc"]
    directory = root / "assets/episode_post/local/music" / ("km-" + isrc.lower())
    url = BASE + "mp3-royaltyfree/" + quote(metadata["filename"], safe="")
    path = directory / "full.mp3"
    download(url, path, HOSTS)
    entry = inspect_asset(root, path, directory, "full")
    entry.update({"id": "km-" + isrc.lower() + "-full", "title": metadata["title"],
                  "artist": "Kevin MacLeod", "variant": "full", "isrc": isrc,
                  "source_url": BASE + "index.html?isrc=" + isrc, "download_url": url,
                  "moods": choice["moods"], "use_cases": choice["use_cases"],
                  "instruments": [s.strip() for s in metadata["instruments"].split(",")],
                  "provider_bpm": metadata.get("bpm"), "provider_feel": metadata.get("feel"),
                  "caution": choice["caution"],
                  "tag_basis": "Official catalog description/feel plus agent inference; NOT_AUDITIONED",
                  "evidence": evidence,
                  "attribution": f'"{metadata["title"]}" Kevin MacLeod (incompetech.com). Licensed under Creative Commons: By Attribution 4.0 License. https://creativecommons.org/licenses/by/4.0/',
                  "license": {"id": "CC-BY-4.0", "url": LICENSE,
                              "usage": "Attribution-required candidate; check actual production/platform use",
                              "provider_notices": ["Use the official attribution code", "No implication of composer endorsement"],
                              "changes_notice_required": True},
                  "status": "TECHNICALLY_VERIFIED_AUDITION_REQUIRED"})
    print(json.dumps({"imported": entry["id"], "title": entry["title"]}), flush=True)
    return entry


def merge_entries(existing: dict, entries: list[dict], selection: dict) -> dict:
    ids = {t["id"] for t in existing["tracks"]}
    hashes = {t["sha256"] for t in existing["tracks"]}
    for entry in entries:
        if entry["id"] in ids or entry["sha256"] in hashes:
            raise ValueError("duplicate entry; refusing to replace annotations or original identities")
        ids.add(entry["id"])
        hashes.add(entry["sha256"])
    return {**existing, "updated_utc": datetime.now(timezone.utc).isoformat(),
            "additional_selections": [*existing.get("additional_selections", []), selection],
            "tracks": [*existing["tracks"], *entries]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    root = args.root.resolve()
    catalog_file = root / "assets/episode_post/music/catalog.json"
    original = catalog_file.read_bytes()
    existing = json.loads(original)
    verify_catalog(root, existing)
    selection_file = root / "assets/episode_post/music/selection-batch-02.json"
    choices = json.loads(selection_file.read_text())["tracks"]
    directory = root / "assets/episode_post/local/music/_evidence/batch-02"
    directory.mkdir(parents=True, exist_ok=True)
    pieces, page, policy = (directory / name for name in
                            ("incompetech-pieces.json", "incompetech-index.html", "incompetech-licenses.html"))
    for url, path in ((BASE + "pieces.json", pieces), (BASE + "index.html?isrc=USUAN1300010", page),
                      (BASE + "licenses/", policy)):
        download(url, path, HOSTS)
    if "By Attribution 4.0" not in page.read_text() or "By Attribution 4.0" not in policy.read_text():
        raise ValueError("reviewed official attribution template is missing")
    metadata = json.loads(pieces.read_text())
    evidence = [identity(root, path) for path in (pieces, page, policy)]
    entries = []
    for choice in choices:
        matches = [item for item in metadata if item["title"] == choice["title"]]
        if len(matches) != 1:
            raise ValueError(f"ambiguous or missing official title: {choice['title']}")
        entries.append(build_entry(root, choice, matches[0], evidence))
    merged = merge_entries(existing, entries, identity(root, selection_file))
    verify_catalog(root, merged)
    backup = root / "assets/episode_post/music/history/catalog-before-batch-02.json"
    backup.parent.mkdir(parents=True, exist_ok=True)
    with backup.open("xb") as handle:
        handle.write(original)
    temporary = catalog_file.with_suffix(".batch-02.pending.json")
    with temporary.open("x") as handle:
        json.dump(merged, handle, indent=2)
        handle.write("\n")
    if hashlib.sha256(catalog_file.read_bytes()).digest() != hashlib.sha256(original).digest():
        raise ValueError("catalog changed concurrently; pending catalog preserved, no overwrite")
    temporary.replace(catalog_file)
    print(json.dumps({"added": len(entries), "total": len(merged["tracks"])}), flush=True)


if __name__ == "__main__":
    main()
