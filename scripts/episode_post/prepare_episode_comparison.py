#!/usr/bin/env python3
"""Freeze neutral EP01 source inputs for separate agent-driven edit runs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from verify_project_assets import verify_assets


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(root: Path) -> dict:
    inventory = json.loads((root / "assets/episode_post/manifest.json").read_text())
    verify_assets(root, inventory, include_local=True)
    base = Path("assets/episode_post/local/pilots/lihun-v21-ep01")
    sources = {}
    for i in range(1, 5):
        unit = f"U{i:02d}"
        folder = base / "units" / f"{unit}-WENXI"
        files = {"path": folder / f"EP01-{unit}-lihun-wenxi_00001-audio.mp4",
                 "prompt": folder / "prompt_h3.txt", "meta": folder / "run_meta.json",
                 "analysis": base / "analysis" / f"{unit}-WENXI.json"}
        record = {k: str(v) for k, v in files.items()}
        record.update({"sha256": digest(root / files["path"]),
                       "prompt_sha256": digest(root / files["prompt"]),
                       "meta_sha256": digest(root / files["meta"]),
                       "analysis_sha256": digest(root / files["analysis"])})
        body = (root / files["prompt"]).read_text().split("【画面内容】", 1)[1].split("【H3 latent", 1)[0]
        record["expected_dialogue"] = [line.strip() for line in re.findall(r"（\s*([A-Za-z][^）]+)）", body)]
        sources[unit] = record
    skill = sorted((root / ".cursor/skills/comfy-h3-episode-assembly").rglob("*.md"))
    preset = "docs/ending-presets/bloom-hold-suspense-v1.json"
    music = base / "music/sb_undertow.mp3"
    return {
        "schema": "episode-edit-comparison/v1", "episode": "EP01", "source_version": "lihun-v21",
        "unit_order": list(sources), "sources": sources,
        "available_music": [{"path": str(music), "sha256": digest(root / music),
                             "title": "Undertow", "artist": "Scott Buckley", "license": "CC-BY 4.0"}],
        "available_presets": [{"path": preset, "sha256": digest(root / preset)}],
        "skill_snapshot": [{"path": str(p.relative_to(root)), "sha256": digest(p)} for p in skill],
        "delivery": {"fps": 24, "width": 768, "height": 1376, "audio_hz": 48000,
                     "language": "en", "lufs": -16, "lufs_tolerance": 0.6, "true_peak_ceiling": -1.5},
        "constraints": ["Keep required dialogue and narrative action; no new generation or external assets.",
                        "Choose cuts, cue timing/levels and ending independently; approved preset is optional.",
                        "No prior candidate output or creative plan is needed as input.",
                        "Record decisions before rendering, then QC and review actual output.",
                        "Not a blinded experiment: historical skill examples and this conversation may influence choices."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    out = root / "assets/episode_post/comparisons/EP01-v21"
    out.mkdir(parents=True, exist_ok=False)
    with (out / "inputs.json").open("x") as handle:
        json.dump(build(root), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(out / "inputs.json")


if __name__ == "__main__":
    main()
