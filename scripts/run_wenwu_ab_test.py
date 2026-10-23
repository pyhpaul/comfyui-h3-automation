#!/usr/bin/env python3
"""A/B test driver: EP17/EP18 x {orig,opt} prompts x {wuxi,wenxi} chains.

IMPORTANT wiring fix vs run_wenwu_test_ep_units.py: in the template's API
graph, bindings send prompt/duration/aspect to orphan nodes (263/259/252)
and MiniMaxH3ReferenceToVideo (265) keeps literal prompt="" / 1344x768 /
length 124. This driver sets 265.prompt / width / height / length directly
from the job fields so the text actually reaches the model, identically for
every config. Everything else (binding, pruning, seed) matches the wenwu
test runner. Outputs stay local under jobs/wenwu_ab_test/ (test artifacts).

Usage:
  COMFY_BASE_URL=http://192.168.50.106:8190 PYTHONPATH=src \
    python scripts/run_wenwu_ab_test.py --chain wuxi --variant orig \
      --episodes EP17 EP18 [--units U01 U02]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from comfy_orch.artifacts import collect_outputs  # noqa: E402
from comfy_orch.binder import apply_bindings, list_media_fields  # noqa: E402
from comfy_orch.client import ComfyClient  # noqa: E402
from comfy_orch.manifest import load_and_validate_job  # noqa: E402
from comfy_orch.prompt_wire import audit_pack_prompt_wiring, wire_pack_prompt  # noqa: E402
from comfy_orch.ui_bind import prune_unused_api_ref_images  # noqa: E402
from run_wenwu_test_ep_units import _wait_history  # noqa: E402

TEMPLATE = "yz_h3_wenwu_test"
JOB_ROOT = ROOT / "jobs" / "ep_units_wenwu_test"
EP_PREFIX = {"EP17": "EP17-兽王降临-wenwu", "EP18": "EP18-秘银碎裂-wenwu"}


def frame_length(duration_seconds: float) -> int:
    n = max(5, round(duration_seconds * 24))
    return n + (5 - (n % 17)) % 17


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain", choices=["wuxi", "wenxi"], required=True)
    ap.add_argument("--variant", choices=["orig", "opt"], required=True)
    ap.add_argument("--episodes", nargs="+", default=["EP17", "EP18"])
    ap.add_argument("--units", nargs="+", default=None)
    ap.add_argument("--out-root", type=Path, default=ROOT / "jobs" / "wenwu_ab_test")
    args = ap.parse_args()

    workflow_path = (ROOT / "templates" / TEMPLATE / "variants" / args.chain
                     / "workflow_api.json")
    workflow_base = json.loads(workflow_path.read_text(encoding="utf-8"))
    template_dir = ROOT / "templates" / TEMPLATE
    bindings_yaml = (template_dir / "bindings.yaml").read_text(encoding="utf-8")
    schema = template_dir / "manifest.schema.yaml"

    base = os.environ.get("COMFY_BASE_URL") or "http://192.168.50.106:8190"
    client = ComfyClient(base)
    stats = client.system_stats()
    device = ((stats.get("devices") or [{}])[0].get("name")) or ""
    if not device:
        raise SystemExit("no CUDA device")
    print(f"READY base={base} gpu={device!r} chain={args.chain} "
          f"variant={args.variant}", flush=True)

    for ep in args.episodes:
        prefix = EP_PREFIX[ep] + ("opt" if args.variant == "opt" else "")
        job_dirs = sorted(JOB_ROOT.glob(f"{prefix}-U*"))
        for job_dir in job_dirs:
            if not job_dir.is_dir():
                continue
            unit = job_dir.name.rsplit("-", 1)[-1]
            if args.units and unit not in args.units:
                continue
            out_dir = args.out_root / f"{args.chain}_{args.variant}" / ep
            out_dir.mkdir(parents=True, exist_ok=True)
            dest = out_dir / f"{ep}-{unit}.mp4"
            if dest.exists():
                print(f"SKIP {dest} (exists)", flush=True)
                continue

            raw = yaml.safe_load((job_dir / "job.yaml").read_text(encoding="utf-8"))
            source = (job_dir / "assets" / "prompt_source.txt").read_text(encoding="utf-8")
            ref_fields = {k: v for k, v in (raw.get("fields") or {}).items()
                          if k.startswith("ref_image_")}
            wired = wire_pack_prompt(source, ref_fields)
            violations = audit_pack_prompt_wiring(source, wired, ref_fields)
            if violations:
                raise RuntimeError(f"{job_dir.name} audit failed: {violations}")
            raw["fields"]["prompt"] = wired

            job = load_and_validate_job(job_dir, schema_path=schema)
            values = dict(job.fields)
            for field in list_media_fields(bindings_yaml):
                if field in job.fields:
                    values[field] = client.upload_image(job.resolve_path(field))

            duration = float(values.get("duration_seconds") or 12.0)
            workflow = json.loads(json.dumps(workflow_base))
            workflow["9001"]["inputs"]["filename_prefix"] = (
                f"h3_context/wenwu_ab/{args.chain}_{args.variant}/{ep.lower()}_{unit.lower()}")
            bound = prune_unused_api_ref_images(
                apply_bindings(workflow, bindings_yaml=bindings_yaml, values=values),
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
            # --- wiring fix: feed 265 directly (identical for all configs)
            bound["265"]["inputs"]["prompt"] = wired
            bound["265"]["inputs"]["width"] = 768
            bound["265"]["inputs"]["height"] = 1344
            bound["265"]["inputs"]["length"] = frame_length(duration)
            bound["364"]["inputs"]["filename_prefix"] = (
                f"{ep}-{unit}-{args.chain}-{args.variant}")
            bound["364"]["inputs"]["save_output"] = True

            print(f"QUEUE {ep}-{unit} chain={args.chain} variant={args.variant} "
                  f"frames={bound['265']['inputs']['length']}", flush=True)
            t0 = time.monotonic()
            prompt_id = client.queue_prompt(bound)
            print(f"QUEUED {ep}-{unit} prompt_id={prompt_id}", flush=True)
            entry = _wait_history(client, prompt_id, f"{ep}-{unit}")
            saved = collect_outputs(client, entry, ROOT / "outputs" / prompt_id,
                                    prefer_node_ids=["364"])
            mp4s = [p for p in saved if p.suffix.lower() == ".mp4"]
            if not mp4s:
                raise RuntimeError(f"{ep}-{unit}: no mp4 {[p.name for p in saved]}")
            dest.write_bytes(mp4s[0].read_bytes())
            meta = {
                "chain": args.chain, "variant": args.variant, "episode": ep,
                "unit": unit, "prompt_id": prompt_id, "duration_seconds": duration,
                "frames": bound["265"]["inputs"]["length"],
                "resolution": "768x1344", "source_job": str(job_dir.relative_to(ROOT)),
                "elapsed_s": round(time.monotonic() - t0),
            }
            (out_dir / f"{ep}-{unit}.run_meta.json").write_text(
                json.dumps(meta, indent=2) + "\n", encoding="utf-8")
            print(f"SAVED {dest} elapsed={meta['elapsed_s']}s", flush=True)
    print(f"BATCH_DONE chain={args.chain} variant={args.variant}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
