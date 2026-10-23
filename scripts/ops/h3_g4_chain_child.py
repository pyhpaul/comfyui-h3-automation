"""Submit one frozen EP04 motion-latent unit inside a G4 chain assignment."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.request import urlopen

import yaml


RUNNER = Path("/content/h3-runner")
sys.path[:0] = [str(RUNNER / "src"), str(RUNNER / "scripts"), "/content"]

import run_ep_units_profiled as runner
from comfy_orch.client import ComfyClient
from h3_a100_ab_child import server_wall_seconds
from h3_g4_chain_contract import validate_graph, validate_job
from h3_g4_chain_media import inspect_latent, inspect_video


def validate_previous_parent(unit: str, parent: str) -> None:
    if unit == "U03":
        return
    previous = f"U{int(unit[1:]) - 1:02d}"
    previous_root = Path("/content/h3-g4-chain") / previous
    receipt = json.loads((previous_root / "phase.json").read_text())
    validation = json.loads((previous_root / "run/validation.json").read_text())
    meta_path = next((previous_root / "run/downloads").rglob("run_meta.json"))
    meta = json.loads(meta_path.read_text())
    if (receipt.get("state") != "success" or receipt.get("archive_state") != "verified"
            or meta.get("latent_path") != parent
            or Path(validation["latent"]["path"]).name != Path(parent).name):
        raise RuntimeError(f"{unit} parent is not the verified {previous} latent")


def main() -> int:
    unit = os.environ["H3_G4_CHAIN_UNIT"]
    parent = os.environ["H3_G4_PARENT_LATENT"]
    if unit not in {"U03", "U04", "U05"}:
        raise RuntimeError(f"unexpected chain unit: {unit}")
    job = RUNNER / "jobs/ep_units" / f"EP04-H3-manual-v16-{unit}" / "job.yaml"
    raw = yaml.safe_load(job.read_text())
    validate_job(raw, unit)
    duration_seconds = int(raw["fields"]["duration_seconds"])
    validate_previous_parent(unit, parent)
    output = Path("/content/h3-g4-chain") / unit / "run"
    output.mkdir(parents=True, exist_ok=False)
    original_queue = ComfyClient.queue_prompt
    submitted = 0

    def queue(self: ComfyClient, workflow: dict) -> str:
        nonlocal submitted
        if submitted:
            raise RuntimeError("only one prompt is permitted per chain unit")
        validate_graph(workflow, unit, parent)
        (output / "submitted_graph.json").write_text(json.dumps(workflow, indent=2) + "\n")
        submitted += 1
        return original_queue(self, workflow)

    ComfyClient.queue_prompt = queue
    os.environ["COMFY_BASE_URL"] = "http://127.0.0.1:8188"
    os.environ.pop("H3_LATENT_SUFFIX", None)
    sys.argv = [sys.argv[0], "--units", unit, "--job-glob", "EP04-H3-manual-v16-{unit}",
                "--continuity", "motion_latent", "--parent-latent", parent,
                "--gpu-profile", "rtx5090", "--download-dir", str(output / "downloads"),
                "--batch-log", str(output / "batch.json")]
    status = runner.main()
    if status:
        return status
    records = json.loads((output / "batch.json").read_text())
    if submitted != 1 or len(records) != 1 or records[0].get("state") != "done":
        raise RuntimeError(f"{unit} expected one completed prompt")
    prompt_id = records[0]["prompt_id"]
    with urlopen(f"http://127.0.0.1:8188/history/{prompt_id}", timeout=20) as response:
        history = json.load(response)
    (output / "history.json").write_text(json.dumps(history, indent=2) + "\n")
    if history[prompt_id].get("status", {}).get("status_str") != "success":
        raise RuntimeError(f"{unit} ComfyUI history did not confirm success")
    latents = list((output / "downloads").rglob("*.safetensors"))
    videos = list((output / "downloads").rglob("*.mp4"))
    if len(latents) != 1 or len(videos) != 1:
        raise RuntimeError(f"{unit} output count: latents={len(latents)} videos={len(videos)}")
    report = {"unit": unit, "gpu_profile": "rtx5090", "prompt_id": prompt_id,
              "server_wall_s": server_wall_seconds(history[prompt_id]),
              "latent": inspect_latent(latents[0], duration_seconds),
              "video": inspect_video(videos[0], duration_seconds)}
    (output / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print("G4_CHAIN_CHILD_OK", unit, prompt_id, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
