"""No-queue admission check of the active Test2 EP02/EP03 G4 runtime."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

import yaml

RUNNER = Path("/content/h3-runner")
sys.path[:0] = [str(RUNNER / "src"), str(RUNNER / "scripts"), "/content"]

from comfy_orch.binder import apply_bindings
from comfy_orch.gpu_adapt import apply_gpu_profile, resolve_gpu_profile
from comfy_orch.manifest import load_and_validate_job
from comfy_orch.prompt_wire import audit_pack_prompt_wiring, wire_pack_prompt
from comfy_orch.render_profile import RenderProfile, apply_render_profile
from comfy_orch.ui_bind import prune_unused_api_ref_images
from h3_test2_ep23_contract import UNITS, job_name, parent_unit, validate_graph, validate_job


def test_unit(episode: str, unit: str, workflow: dict, bindings: str) -> dict:
    job_dir = RUNNER / "jobs/ep_units" / job_name(episode, unit)
    raw = yaml.safe_load((job_dir / "job.yaml").read_text(encoding="utf-8"))
    validate_job(raw, episode, unit)
    load_and_validate_job(job_dir, schema_path=RUNNER / "templates/yz_h3_ep_unit/manifest.schema.yaml")
    fields = raw["fields"]
    refs = {key: value for key, value in fields.items() if key.startswith("ref_image_")}
    source = (job_dir / "assets/prompt_source.txt").read_text(encoding="utf-8")
    wired = wire_pack_prompt(source, refs)
    if wired != fields["prompt"] or audit_pack_prompt_wiring(source, wired, refs):
        raise RuntimeError(f"{episode} {unit} prompt/refs differ from accepted job")
    values = dict(fields)
    for index in range(len(refs)):
        values[f"ref_image_{index}"] = f"preflight-upload-{index}.png"
    bound = prune_unused_api_ref_images(
        apply_bindings(workflow, bindings_yaml=bindings, values=values), values=values)
    parent = parent_unit(episode, unit)
    parent_path = (f"h3_context/{episode.lower()}_{parent.lower()}_00001.safetensors"
                   if parent else None)
    profile = RenderProfile(
        continuity="motion_latent", save_clip_index=int(unit[1:]),
        load_clip_index=int(parent[1:]) if parent else 0,
        motion_latent_path=parent_path,
        latent_filename_prefix=f"h3_context/{episode.lower()}_{unit.lower()}",
    )
    graph = apply_gpu_profile(
        apply_render_profile(bound, profile, filename_prefix=values["filename_prefix"]),
        resolve_gpu_profile("rtx5090"),
    )
    validate_graph(graph, episode, unit, parent_path, len(refs))
    return {"episode": episode, "unit": unit, "refs": len(refs),
            "parent": parent, "graph_nodes": len(graph)}


def main() -> None:
    manifest = Path("/content/test2-ep23-input-manifest.json")
    installed = json.loads(Path("/content/test2-ep23-inputs.json").read_text())
    if installed.get("state") != "ready":
        raise RuntimeError("accepted Test2 jobs were not installed")
    template = RUNNER / "templates/yz_h3_ep_unit"
    workflow = json.loads((template / "workflow_api.json").read_text(encoding="utf-8"))
    bindings = (template / "bindings.yaml").read_text(encoding="utf-8")
    records = [test_unit(ep, unit, workflow, bindings)
               for ep, units in UNITS.items() for unit in units]
    with urlopen("http://127.0.0.1:8188/system_stats", timeout=10) as response:
        stats = json.load(response)
    device = stats["devices"][0]["name"]
    if "RTX PRO 6000" not in device:
        raise RuntimeError(f"active ComfyUI GPU changed: {device}")
    with urlopen("http://127.0.0.1:8188/object_info", timeout=30) as response:
        nodes = json.load(response)
    required = {
        "MiniMaxH3ReferenceToVideo", "MiniMaxH3MemoryEfficientSageAttentionPatch",
        "MiniMaxH3MotionContextSaveLatent", "MiniMaxH3MotionContextLoadLatent",
        "MiniMaxH3MotionContext", "MiniMaxH3MotionContextTrim",
    }
    if not required.issubset(nodes):
        raise RuntimeError(f"active ComfyUI H3 nodes missing: {sorted(required - nodes.keys())}")
    with urlopen("http://127.0.0.1:8188/queue", timeout=10) as response:
        queue = json.load(response)
    if queue.get("queue_running") or queue.get("queue_pending"):
        raise RuntimeError("no-queue preflight found an existing ComfyUI prompt")
    report = {
        "state": "ready", "device": device, "units": records,
        "input_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "runtime_api9_sha256": installed["runtime_api9_sha256"],
        "queued_prompts": 0,
    }
    output = Path("/content/test2-ep23-preflight.json")
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    remote = os.environ.get("H3_TEST2_REMOTE")
    if remote:
        subprocess.run(["/content/rclone", "copyto", str(output), f"{remote}/preflight.json",
                        "--config", "/content/rclone.conf"], check=True, timeout=120)
    print("TEST2_EP23_PREFLIGHT_OK", json.dumps({"units": len(records), "device": device}),
          flush=True)


if __name__ == "__main__":
    main()
