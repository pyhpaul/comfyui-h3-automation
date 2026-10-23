#!/usr/bin/env python3
"""Import a small curated, official-source music pool without changing episode edits."""
from __future__ import annotations

import argparse
from array import array
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import subprocess
import sys
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from ep_pilot_media import loudness, probe

BASE = "https://www.scottbuckley.com.au/library/"
LICENSE = "https://creativecommons.org/licenses/by/4.0/"


class AudioLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if tag == "a" and key == "href" and value and urlparse(value).path.endswith(".mp3"):
                if value not in self.links:
                    self.links.append(value)


def download(url: str, path: Path,
             allowed_hosts: frozenset[str] = frozenset({"www.scottbuckley.com.au", "creativecommons.org"})) -> None:
    if path.exists():
        return
    if urlparse(url).hostname not in allowed_hosts:
        raise ValueError("URL is outside the reviewed source allowlist")
    path.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "EpisodeMusicAssetImporter/1.0"})
    temporary = path.with_suffix(path.suffix + ".part")
    if temporary.exists():
        raise ValueError(f"incomplete prior download requires inspection: {temporary}")
    with urlopen(request, timeout=90) as response, temporary.open("xb") as handle:
        if urlparse(response.url).hostname not in allowed_hosts:
            raise ValueError("redirect leaves reviewed source allowlist")
        size = 0
        while chunk := response.read(256 * 1024):
            size += len(chunk)
            if size > 40 * 1024 * 1024:
                raise ValueError("asset exceeds the 40 MiB per-file budget")
            handle.write(chunk)
    temporary.rename(path)


def identity(root: Path, path: Path) -> dict:
    return {"path": str(path.relative_to(root)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size}


def energy_candidates(path: Path) -> list[dict]:
    decoded = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ar", "8000",
                              "-ac", "1", "-f", "f32le", "-"], capture_output=True, check=True)
    data = array("f")
    data.frombytes(decoded.stdout)
    if sys.byteorder != "little":
        data.byteswap()
    windows = []
    width = 20 * 8000
    for first in range(5 * 8000, len(data) - width + 1, 10 * 8000):
        rms = math.sqrt(sum(x * x for x in data[first:first + width]) / width)
        windows.append({"start": first / 8000, "end": (first + width) / 8000,
                        "rms_dbfs": round(20 * math.log10(max(rms, 1e-12)), 2)})
    if not windows:
        raise ValueError("source too short for candidate windows")
    ranked = sorted(windows, key=lambda item: item["rms_dbfs"])
    return [{**ranked[index], "role": role, "status": "ENERGY_CANDIDATE_NOT_AUDITIONED",
             "basis": "20-second RMS window; not a phrase boundary, mood or beat detector"}
            for role, index in (("lower-energy", 0), ("middle-energy", len(ranked) // 2),
                                ("higher-energy", -1))]


def import_track(root: Path, track: dict, policy: Path) -> list[dict]:
    directory = root / "assets/episode_post/local/music" / ("sb-" + track["slug"])
    page = directory / "source-page.html"
    source_url = BASE + track["slug"] + "/"
    download(source_url, page)
    html = page.read_text()
    if "creativecommons.org/licenses/by/4.0" not in html or "Attribution format" not in html:
        raise ValueError(f"missing track-specific licensing evidence: {source_url}")
    parser = AudioLinks()
    parser.feed(html)
    links = [urljoin(source_url, link) for link in parser.links]
    count = 2 if track.get("include_no_piano_mix") else 1
    if len(links) != count:
        raise ValueError(f"review required: expected {count} official MP3 links, found {links}")
    results = []
    for i, url in enumerate(links):
        variant = "full" if i == 0 else "no-piano-melody"
        path = root / track["existing"] if track.get("existing") else directory / (variant + ".mp3")
        if not track.get("existing"):
            download(url, path)
        result = inspect_asset(root, path, directory, variant)
        result.update({"id": "sb-" + track["slug"] + "-" + variant,
                       "title": track["title"], "artist": "Scott Buckley", "variant": variant,
                       "source_url": source_url, "download_url": url,
                       "moods": track["moods"], "instruments": track["instruments"],
                       "use_cases": track["use_cases"], "caution": track["caution"],
                       "tag_basis": "Official composer description plus agent inference; NOT_AUDITIONED",
                       "evidence": [identity(root, page), identity(root, policy)],
                       "attribution": f"'{track['title']}' by Scott Buckley - released under CC-BY 4.0. www.scottbuckley.com.au",
                       "license": {"id": "CC-BY-4.0", "url": LICENSE,
                                   "usage": "Attribution-required synchronized-media candidate; no blanket platform clearance",
                                   "provider_notices": ["Credit in YouTube description", "Do not resell isolated audio",
                                                        "Do not reupload to music streaming services",
                                                        "Do not enroll source/remixes in audio fingerprinting services"],
                                   "changes_notice_required": True},
                       "status": "TECHNICALLY_VERIFIED_AUDITION_REQUIRED"})
        results.append(result)
        print(json.dumps({"imported": result["id"], "seconds": result["technical"]["duration_s"]}), flush=True)
    return results


def inspect_asset(root: Path, path: Path, directory: Path, variant: str) -> dict:
    logs = directory / "analysis"
    info = probe(path, logs / f"{variant}-probe.log")
    audio = next(s for s in info["streams"] if s["codec_type"] == "audio")
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-vn", "-f", "null", "-"], check=True)
    level = loudness(path, logs / f"{variant}-loudness.log")
    return {**identity(root, path), "technical": {"duration_s": float(info["format"]["duration"]),
            "codec": audio["codec_name"], "sample_rate": int(audio["sample_rate"]),
            "channels": audio["channels"], "integrated_lufs": float(level["input_i"]),
            "true_peak_dbtp": float(level["input_tp"]), "full_decode_passed": True},
            "candidate_segments": energy_candidates(path), "realtime_listening": "NOT_DONE"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    root = args.root.resolve()
    selection = json.loads((root / "assets/episode_post/music/selection.json").read_text())
    catalog = root / "assets/episode_post/music/catalog.json"
    if catalog.exists():
        raise ValueError("catalog already exists; do not overwrite curated annotations")
    policy = root / "assets/episode_post/local/music/_evidence/using-this-music.html"
    download(BASE + "using-this-music/", policy)
    download(LICENSE, policy.with_name("cc-by-4.0.html"))
    tracks = []
    for track in selection["tracks"]:
        tracks.extend(import_track(root, track, policy))
    with catalog.open("x") as handle:
        json.dump({"schema": "episode-music-catalog/v1", "created_utc": datetime.now(timezone.utc).isoformat(),
                   "ownership": "Local project-held licensed files; copyright remains with composers",
                   "selection": identity(root, root / "assets/episode_post/music/selection.json"),
                   "scope": "Candidate pool only; no edits or frozen comparison contracts changed",
                   "tracks": tracks}, handle, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
