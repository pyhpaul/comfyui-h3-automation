#!/usr/bin/env python3
"""Build the lihun v23 fix-round input bundle (seed-batch re-renders).

For every FAIL unit in runs/lihun_v23_fix_plan.md, emit N candidate
units (tags EPxx-UyyC1..CN) into .cache/lihun_v23_fix1/input/, copying
workflow/prompt/assets from the original production pack and replacing
only the workflow seed. Prompts, durations and chain fields stay
identical to production (fix standard: seed batch first, prompt surgery
only for structural problems). Candidate seeds are derived
deterministically from sha256("lihun-fix1-<tag>-C<i>") so the pack is
reproducible and never collides with the production seed segment.

The bundle is consumed by colab_h3_lihun_batch_host.py --extra-input
with a fix-specific --remote-name / --feiniu-batch, so candidates land
in their own Drive namespace and Feiniu fix folder.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache"
OUT = CACHE / "lihun_v23_fix1" / "input"
CANDIDATES = 3

FAIL_UNITS = [
    "EP03-U02", "EP05-U04", "EP42-U03", "EP11-U04", "EP43-U06",
    "EP13-U01", "EP44-U07", "EP45-U01", "EP14-U01", "EP14-U03",
    "EP46-U01", "EP15-U04", "EP16-U01", "EP16-U03", "EP47-U03",
    "EP18-U09", "EP19-U06", "EP20-U03", "EP51-U02", "EP53-U01",
    "EP54-U01", "EP57-U01", "EP57-U08", "EP58-U06",
    "EP26-U01",
    "EP64-U03",
    "EP64-U05",
    "EP65-U01",
    "EP29-U03",
]


def candidate_seed(tag: str) -> int:
    digest = hashlib.sha256(f"lihun-fix1-{tag}".encode()).digest()
    return int.from_bytes(digest[:8], "big") & (2**63 - 1)


def find_source(tag: str) -> tuple[Path, dict]:
    packs = [CACHE / "lihun_v23_colab" / "input"]
    packs += sorted(CACHE.glob("lihun_v23_colab_ep*/input"))
    for pack in packs:
        manifest = pack / "units.json"
        if not manifest.is_file():
            continue
        for unit in json.loads(manifest.read_text())["units"]:
            if unit["tag"] == tag:
                return pack, unit
    raise SystemExit(f"source pack not found for {tag}")


def replace_seed(workflow: Path, old_seed: int, new_seed: int) -> str:
    text = workflow.read_text()
    needle = f'"seed": {old_seed}'
    if text.count(needle) != 1:
        raise SystemExit(f"{workflow}: seed occurrences={text.count(needle)}")
    return text.replace(needle, f'"seed": {new_seed}')


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "workflows").mkdir(parents=True)
    (OUT / "prompts").mkdir()
    (OUT / "assets").mkdir()
    units = []
    for tag in FAIL_UNITS:
        pack, src = find_source(tag)
        shutil.copy2(pack / src["prompt_file"], OUT / src["prompt_file"])
        for blob in src["assets"]:
            dst = OUT / "assets" / blob
            if not dst.exists():
                shutil.copy2(pack / "assets" / blob, dst)
        for idx in range(1, CANDIDATES + 1):
            ctag = f"{tag}C{idx}"
            seed = candidate_seed(ctag)
            wf_name = f"workflows/{ctag}.json"
            (OUT / wf_name).write_text(replace_seed(
                pack / src["workflow"], int(src["seed"]), seed))
            entry = dict(src)
            entry.update({
                "tag": ctag,
                "seed": seed,
                "workflow": wf_name,
                "job": f"{src['job']}-fix1c{idx}",
                "fix_of": tag,
                "candidate": idx,
            })
            units.append(entry)
    (OUT / "units.json").write_text(json.dumps(
        {"units": units}, ensure_ascii=False, indent=1) + "\n")
    print(f"fix bundle: {len(units)} candidates for "
          f"{len(FAIL_UNITS)} units -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
