#!/usr/bin/env python3
"""TEST: wenwu U02 with an external second pass (latent upscale + resample).

Same binding as run_wenwu_test_ep_units, then appends the profiled-style
pass2 chain after SelfLiftH3Sampler (397):
  SeparateAV -> LatentUpscaler3D x1.5 -> ConcatAV -> SamplerCustomAdvanced
  (BasicGuider on the base H3 conditioning, low sigmas) -> decode -> 364.

Usage:
  COMFY_BASE_URL=http://192.168.50.106:8190 PYTHONPATH=src \
    python scripts/run_wenwu_pass2_test.py --units U02 \
      --out-dir jobs/facerefine_test/pass2_U02
"""
from __future__ import annotations

import argparse
import json
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
from comfy_orch.named_assets_bind import motion_latent_prefix  # noqa: E402
from comfy_orch.prompt_wire import audit_pack_prompt_wiring, wire_pack_prompt  # noqa: E402
from comfy_orch.ui_bind import prune_unused_api_ref_images  # noqa: E402
from run_wenwu_test_ep_units import _wait_history  # noqa: E402

TEMPLATE = "yz_h3_wenwu_test"
JOB_ROOT = ROOT / "jobs" / "ep_units_wenwu_test"
LATENT_ROOT = "h3_context/wenwu_test"


def add_second_pass(workflow: dict, *, unit_name: str, scale: float = 1.5) -> dict:
    out = json.loads(json.dumps(workflow))
    out["9101"] = {"class_type": "easy float", "inputs": {"value": float(scale)}}
    out["9102"] = {
        "class_type": "LTXVSeparateAVLatent",
        "inputs": {"av_latent": ["397", 0]},
    }
    out["9103"] = {
        "class_type": "MinimaxH3LatentUpscaler3D",
        "inputs": {
            "latent": ["9102", 0],
            "model_name": "minimax_h3_latent_upscaler_3d_fp16.safetensors",
            "mode": "scale by multiplier",
            "mode.scale": ["9101", 0],
            "align": 32,
            "enable_temporal_chunking": True,
            "force_unload": True,
            "device": "cuda",
            "precision": "fp16",
        },
    }
    out["9104"] = {
        "class_type": "LTXVConcatAVLatent",
        "inputs": {"video_latent": ["9103", 0], "audio_latent": ["9102", 1]},
    }
    out["9105"] = {
        "class_type": "BasicGuider",
        "inputs": {"model": ["329", 0], "conditioning": ["265", 0]},
    }
    out["9106"] = {
        "class_type": "SplitSigmas",
        "inputs": {"sigmas": ["261", 0], "step": 5},
    }
    out["9107"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": 42}}
    out["9108"] = {
        "class_type": "SamplerCustomAdvanced",
        "inputs": {
            "noise": ["9107", 0],
            "guider": ["9105", 0],
            "sampler": ["255", 0],
            "sigmas": ["9106", 1],
            "latent_image": ["9104", 0],
        },
    }
    out["9109"] = {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["9108", 1], "vae": ["36", 0]},
    }
    out["9110"] = {
        "class_type": "VAEDecodeAudio",
        "inputs": {"samples": ["9108", 1], "vae": ["37", 0]},
    }
    out["364"]["inputs"]["images"] = ["9109", 0]
    out["364"]["inputs"]["audio"] = ["9110", 0]
    out["364"]["inputs"]["filename_prefix"] = f"{unit_name}-wenwu-pass2"
    out["364"]["inputs"]["save_output"] = True
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--units", nargs="+", default=["U02"])
    ap.add_argument("--job-prefix", default="EP01-黑手党老大-v2")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--pass2-scale", type=float, default=1.5)
    args = ap.parse_args()

    import os

    base = os.environ.get("COMFY_BASE_URL") or "http://192.168.50.106:8190"
    client = ComfyClient(base)
    stats = client.system_stats()
    device = ((stats.get("devices") or [{}])[0].get("name")) or ""
    if not device:
        raise SystemExit("no CUDA device")
    print(f"READY base={base} gpu={device!r} pass2_scale={args.pass2_scale}", flush=True)

    template_dir = ROOT / "templates" / TEMPLATE
    workflow_base = json.loads((template_dir / "workflow_api.json").read_text(encoding="utf-8"))
    bindings_yaml = (template_dir / "bindings.yaml").read_text(encoding="utf-8")
    schema = template_dir / "manifest.schema.yaml"

    for unit in args.units:
        unit = unit.strip().upper()
        job_dir = JOB_ROOT / f"{args.job_prefix}-{unit}"
        raw = yaml.safe_load((job_dir / "job.yaml").read_text(encoding="utf-8"))
        source = (job_dir / "assets" / "prompt_source.txt").read_text(encoding="utf-8")
        ref_fields = {
            k: v for k, v in (raw.get("fields") or {}).items() if k.startswith("ref_image_")
        }
        wired = wire_pack_prompt(source, ref_fields)
        violations = audit_pack_prompt_wiring(source, wired, ref_fields)
        if violations:
            raise RuntimeError(f"{unit} audit failed: {violations}")
        raw["fields"]["prompt"] = wired

        job = load_and_validate_job(job_dir, schema_path=schema)
        values = dict(job.fields)
        for field in list_media_fields(bindings_yaml):
            if field in job.fields:
                values[field] = client.upload_image(job.resolve_path(field))

        episode = str(raw.get("episode") or "")
        unit_name = values.get("filename_prefix") or f"{episode}-{unit}"
        latent_prefix = f"{LATENT_ROOT}/{motion_latent_prefix(episode, unit)}"

        workflow = json.loads(json.dumps(workflow_base))
        if "9001" in workflow:
            workflow["9001"]["inputs"]["filename_prefix"] = latent_prefix
        bound = prune_unused_api_ref_images(
            apply_bindings(workflow, bindings_yaml=bindings_yaml, values=values),
            values=values,
        )
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
        bound = add_second_pass(keep, unit_name=unit_name, scale=args.pass2_scale)

        print(f"QUEUE {unit_name}-pass2", flush=True)
        prompt_id = client.queue_prompt(bound)
        print(f"QUEUED {unit_name} prompt_id={prompt_id}", flush=True)
        entry = _wait_history(client, prompt_id, unit_name)

        out_dir = ROOT / "outputs" / prompt_id
        saved = collect_outputs(client, entry, out_dir, prefer_node_ids=["364"])
        mp4s = [p for p in saved if p.suffix.lower() == ".mp4"]
        if not mp4s:
            raise RuntimeError(f"no mp4 in outputs {[p.name for p in saved]}")
        args.out_dir.mkdir(parents=True, exist_ok=True)
        dest = args.out_dir / mp4s[0].name
        dest.write_bytes(mp4s[0].read_bytes())
        (args.out_dir / "run_meta.json").write_text(json.dumps({
            "test": "wenwu_pass2", "unit": unit_name, "prompt_id": prompt_id,
            "second_pass": True, "pass2_scale": args.pass2_scale,
            "mp4": str(dest),
        }, indent=2) + "\n", encoding="utf-8")
        print(f"SAVED {dest}", flush=True)
        print(f"SUCCESS {unit_name} prompt_id={prompt_id}", flush=True)
    print("BATCH_DONE wenwu_pass2_test", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
