"""Submit exactly one frozen motion-latent U02 with a pre-submit graph parity gate."""

import copy
import json
import os
import sys
from pathlib import Path
from urllib.request import urlopen


RUNNER = Path("/content/h3-runner")
OUTPUT = Path("/content/h3-g4-u02/run")
sys.path[:0] = [str(RUNNER / "src"), str(RUNNER / "scripts"), "/content"]

import run_ep_units_profiled as runner
from comfy_orch.client import ComfyClient
from h3_a100_ab_child import inspect_latent, inspect_video, server_wall_seconds
from h3_a100_ab_contract import graphs_match_except_output_prefix


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=False)
    baseline = json.loads(Path("/content/g4-c1-reference-graph.json").read_text())
    original_queue = ComfyClient.queue_prompt
    submitted = 0

    def queue(self: ComfyClient, workflow: dict) -> str:
        nonlocal submitted
        if submitted:
            raise RuntimeError("G4 trial permits only one U02 prompt")
        graph = copy.deepcopy(workflow)
        graph["264"]["inputs"]["filename_prefix"] += "-g4-u02"
        if not graphs_match_except_output_prefix(baseline, graph):
            raise RuntimeError("G4 graph differs from approved C1 graph beyond output prefixes")
        (OUTPUT / "submitted_graph.json").write_text(json.dumps(graph, indent=2) + "\n")
        submitted += 1
        return original_queue(self, graph)

    ComfyClient.queue_prompt = queue
    os.environ["COMFY_BASE_URL"] = "http://127.0.0.1:8188"
    os.environ["H3_LATENT_SUFFIX"] = "g4_u02"
    sys.argv = [sys.argv[0], "--units", "U02", "--job-glob", "EP04-H3-manual-v16-{unit}",
                "--continuity", "motion_latent", "--parent-latent",
                "h3_context/ep04_u01_00001.safetensors", "--gpu-profile", "rtx5090",
                "--download-dir", str(OUTPUT / "downloads"),
                "--batch-log", str(OUTPUT / "batch.json")]
    status = runner.main()
    if status:
        return status
    records = json.loads((OUTPUT / "batch.json").read_text())
    if submitted != 1 or len(records) != 1 or records[0]["state"] != "done":
        raise RuntimeError("expected exactly one completed U02 record")
    prompt_id = records[0]["prompt_id"]
    with urlopen(f"http://127.0.0.1:8188/history/{prompt_id}", timeout=20) as response:
        history = json.load(response)
    (OUTPUT / "history.json").write_text(json.dumps(history, indent=2) + "\n")
    if history[prompt_id].get("status", {}).get("status_str") != "success":
        raise RuntimeError("ComfyUI history did not confirm success")
    latents = list((OUTPUT / "downloads").rglob("*.safetensors"))
    videos = list((OUTPUT / "downloads").rglob("*.mp4"))
    if len(latents) != 1 or len(videos) != 1:
        raise RuntimeError(f"unexpected output count: latents={len(latents)} videos={len(videos)}")
    report = {"gpu_profile": "rtx5090", "prompt_id": prompt_id,
              "server_wall_s": server_wall_seconds(history[prompt_id]),
              "latent": inspect_latent(latents[0]), "video": inspect_video(videos[0])}
    (OUTPUT / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print("G4_U02_CHILD_OK", prompt_id, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
