#!/usr/bin/env python3
"""Prepare Colab production bundle for Chaofu fx21 (EP01-EP06, wenxi).

Locally binds every unit's wenxi workflow exactly like
scripts/run_chaofu_wenxi.py does at submit time (same binder, pruning,
motion-latent graft with statically predicted parent latent paths),
dedupes asset blobs by content SHA, and writes a bundle the Colab
guest phase can execute without comfy_orch:

  .cache/chaofu_fx21_colab/input/
    units.json            per-unit manifest (order = render order)
    assets/<sha16>.png    unique asset blobs
    workflows/<EP>-<U>.json
    prompts/<EP>-<U>.txt  wired prompt (prompt_h3.txt content)

Does not queue anything.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from comfy_orch.binder import apply_bindings, list_media_fields  # noqa: E402
from comfy_orch.manifest import load_and_validate_job  # noqa: E402
from comfy_orch.prompt_wire import audit_pack_prompt_wiring, wire_pack_prompt  # noqa: E402
from comfy_orch.ui_bind import prune_unused_api_ref_images  # noqa: E402
from run_lihun_wenxi import (  # noqa: E402
    JOB_ROOT,
    LATENT_ROOT,
    TEMPLATE_DIR,
    frame_length,
    graft_motion_latent,
    unit_index,
)

OUT = ROOT / ".cache" / "lihun_v23_colab" / "input"
EPISODES = ["EP01", "EP02", "EP03", "EP04", "EP05"]


def main() -> int:
    workflow_base = json.loads(
        (TEMPLATE_DIR / "variants" / "wenxi" / "workflow_api.json")
        .read_text(encoding="utf-8"))
    bindings_yaml = (TEMPLATE_DIR / "bindings.yaml").read_text(encoding="utf-8")
    schema = TEMPLATE_DIR / "manifest.schema.yaml"

    (OUT / "assets").mkdir(parents=True, exist_ok=True)
    (OUT / "workflows").mkdir(parents=True, exist_ok=True)
    (OUT / "prompts").mkdir(parents=True, exist_ok=True)

    blob_by_sha: dict[str, str] = {}
    units_out = []
    total_jobs = 0
    for ep in EPISODES:
        jobs = sorted(JOB_ROOT.glob(f"{ep}-继母-v23-U*"))
        if not jobs:
            raise SystemExit(f"no jobs for {ep}")
        prev_latent: str | None = None
        for job_dir in jobs:
            unit = job_dir.name.rsplit("-", 1)[-1]
            raw = yaml.safe_load((job_dir / "job.yaml").read_text(encoding="utf-8"))
            source = (job_dir / "assets" / "prompt_source.txt").read_text(encoding="utf-8")
            ref_fields = {k: v for k, v in (raw.get("fields") or {}).items()
                          if k.startswith("ref_image_")}
            wired = wire_pack_prompt(source, ref_fields)
            violations = audit_pack_prompt_wiring(source, wired, ref_fields)
            if violations:
                raise SystemExit(f"{job_dir.name} audit failed: {violations}")
            raw["fields"]["prompt"] = wired
            job = load_and_validate_job(job_dir, schema_path=schema)

            values = dict(job.fields)
            asset_blobs: list[str] = []
            for field in list_media_fields(bindings_yaml):
                if field not in job.fields:
                    continue
                path = job.resolve_path(field)
                data = path.read_bytes()
                sha = hashlib.sha256(data).hexdigest()
                blob = blob_by_sha.get(sha)
                if blob is None:
                    blob = f"{sha[:16]}{path.suffix.lower()}"
                    (OUT / "assets" / blob).write_bytes(data)
                    blob_by_sha[sha] = blob
                values[field] = blob
                if blob not in asset_blobs:
                    asset_blobs.append(blob)

            episode = str(raw.get("episode") or "")
            ep_code = episode.split("-")[0]
            start_mode = str(raw.get("start_mode") or "independent")
            if start_mode == "independent":
                prev_latent = None
            duration = float(values.get("duration_seconds") or 15.083)
            latent_prefix = f"{LATENT_ROOT}/{ep_code.lower()}_{unit.lower()}"
            latent_rel = (f"{latent_prefix}_{unit_index(unit):05d}"
                          f".safetensors")

            workflow = json.loads(json.dumps(workflow_base))
            workflow["9001"]["inputs"]["filename_prefix"] = latent_prefix
            workflow["9001"]["inputs"]["clip_index"] = unit_index(unit)
            bound = prune_unused_api_ref_images(
                apply_bindings(workflow, bindings_yaml=bindings_yaml,
                               values=values),
                values=values)
            keep = {}
            for nid, node in bound.items():
                ct = node.get("class_type")
                inputs = node.get("inputs") or {}
                if ct == "LoadAudio" and inputs.get("audio") in (None, "None", ""):
                    continue
                if ct == "VHS_LoadVideo" and not inputs.get("video"):
                    continue
                if ct == "LoadImage" and inputs.get("image") in (None, "None", ""):
                    continue
                keep[nid] = node
            bound = keep
            bound["265"]["inputs"]["prompt"] = wired
            bound["265"]["inputs"]["width"] = 768
            bound["265"]["inputs"]["height"] = 1376
            bound["265"]["inputs"]["length"] = frame_length(duration)
            seed = random.randrange(0, 2**63 - 1)
            bound["397"]["inputs"]["seed"] = seed
            bound["364"]["inputs"]["filename_prefix"] = (
                f"{ep_code}-{unit}-lihun-wenxi")
            bound["364"]["inputs"]["save_output"] = True
            parent_latent = None
            if start_mode != "independent":
                if prev_latent is None:
                    raise SystemExit(
                        f"{job_dir.name}: parent_latent unit without parent")
                parent_latent = prev_latent
                graft_motion_latent(bound, parent_latent, unit_index(unit) - 1)

            tag = f"{ep_code}-{unit}"
            (OUT / "workflows" / f"{tag}.json").write_text(
                json.dumps(bound, ensure_ascii=False, indent=1), encoding="utf-8")
            (OUT / "prompts" / f"{tag}.txt").write_text(wired, encoding="utf-8")
            units_out.append({
                "tag": tag, "episode": ep_code, "unit": unit,
                "job": job_dir.name, "seed": seed,
                "start_mode": start_mode,
                "parent_latent": parent_latent,
                "latent_rel": latent_rel,
                "duration_seconds": duration,
                "assets": asset_blobs,
                "workflow": f"workflows/{tag}.json",
                "prompt_file": f"prompts/{tag}.txt",
            })
            prev_latent = latent_rel
            total_jobs += 1

    (OUT / "units.json").write_text(
        json.dumps({"units": units_out}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    total_bytes = sum(p.stat().st_size for p in (OUT / "assets").iterdir())
    print(f"PREP_OK units={total_jobs} unique_blobs={len(blob_by_sha)} "
          f"asset_bytes={total_bytes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
