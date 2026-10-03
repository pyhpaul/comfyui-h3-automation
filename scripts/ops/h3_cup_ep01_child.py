"""Submit and validate one cup EP01 unit on the restored G4 runtime."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

import yaml


RUNNER = Path("/content/h3-runner")
OUTPUT_ROOT = Path("/content/h3-cup-ep01")
sys.path[:0] = [str(RUNNER / "src"), str(RUNNER / "scripts"), "/content"]

import run_ep_units_profiled as runner
from comfy_orch.client import ComfyClient
from h3_cup_ep01_contract import PARENTS, job_name, validate_graph, validate_job
from h3_cup_ep01_media import inspect_latent, inspect_video


def server_wall_seconds(entry: dict) -> float:
    stamps = {name: details["timestamp"] for name, details in entry["status"]["messages"]
              if name in {"execution_start", "execution_success"}}
    if set(stamps) != {"execution_start", "execution_success"}:
        raise RuntimeError("missing ComfyUI execution start/success timestamps")
    return round((stamps["execution_success"] - stamps["execution_start"]) / 1000, 3)


def verify_local_parent(unit: str, parent_path: str | None) -> None:
    expected = PARENTS[unit]
    if expected is None:
        if parent_path:
            raise RuntimeError(f"{unit} must start without a parent latent")
        return
    previous = OUTPUT_ROOT / expected
    receipt = json.loads((previous / "phase.json").read_text(encoding="utf-8"))
    validation = json.loads((previous / "run/validation.json").read_text(encoding="utf-8"))
    if (
        receipt.get("state") not in {"success", "recovered"}
        or receipt.get("archive_state") != "verified"
        or validation.get("latent_output_relative") != parent_path
        or not validation.get("latent", {}).get("sha256")
    ):
        raise RuntimeError(f"{unit} parent is not the verified {expected} latent")


def runner_args(unit: str, parent_path: str | None, output: Path) -> list[str]:
    args = [
        "h3_cup_ep01_child.py", "--units", unit,
        "--job-glob", job_name(unit), "--continuity", "motion_latent",
        "--gpu-profile", "rtx5090", "--download-dir", str(output / "downloads"),
        "--batch-log", str(output / "batch.json"),
    ]
    if parent_path:
        args.extend(("--parent-latent", parent_path))
    return args


def make_review_frames(video: Path, output: Path) -> None:
    subprocess.run([
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video), "-vf", "fps=1/3,scale=384:-1,tile=3x2",
        "-frames:v", "1", str(output / "contact-sheet.jpg"),
    ], check=True, timeout=90)
    subprocess.run([
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", "0.5", "-i", str(video), "-frames:v", "1",
        str(output / "first-frame.jpg"),
    ], check=True, timeout=90)
    subprocess.run([
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-sseof", "-0.15", "-i", str(video), "-frames:v", "1",
        str(output / "last-frame.jpg"),
    ], check=True, timeout=90)
    if not (output / "last-frame.jpg").is_file():
        raise RuntimeError("last-frame.jpg was not written")


def main() -> int:
    unit = os.environ["H3_CUP_UNIT"]
    if unit not in PARENTS:
        raise RuntimeError(f"unexpected cup EP01 unit: {unit}")
    parent_path = os.environ.get("H3_CUP_PARENT_LATENT") or None
    job_dir = RUNNER / "jobs/ep_units" / job_name(unit)
    raw = yaml.safe_load((job_dir / "job.yaml").read_text(encoding="utf-8"))
    validate_job(raw, unit)
    verify_local_parent(unit, parent_path)
    output = OUTPUT_ROOT / unit / "run"
    output.mkdir(parents=True, exist_ok=False)
    original_queue = ComfyClient.queue_prompt
    submitted = 0

    def queue(self: ComfyClient, workflow: dict) -> str:
        nonlocal submitted
        if submitted:
            raise RuntimeError("only one prompt is permitted per cup unit")
        validate_graph(workflow, unit, parent_path)
        (output / "submitted_graph.json").write_text(
            json.dumps(workflow, indent=2) + "\n", encoding="utf-8")
        submitted += 1
        return original_queue(self, workflow)

    ComfyClient.queue_prompt = queue
    os.environ["COMFY_BASE_URL"] = "http://127.0.0.1:8188"
    os.environ.pop("H3_LATENT_SUFFIX", None)
    sys.argv = runner_args(unit, parent_path, output)
    status = runner.main()
    if status:
        return status
    records = json.loads((output / "batch.json").read_text(encoding="utf-8"))
    if submitted != 1 or len(records) != 1 or records[0].get("state") != "done":
        raise RuntimeError(f"{unit} expected one completed prompt")
    prompt_id = records[0]["prompt_id"]
    with urlopen(f"http://127.0.0.1:8188/history/{prompt_id}", timeout=20) as response:
        history = json.load(response)
    (output / "history.json").write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")
    if history[prompt_id].get("status", {}).get("status_str") != "success":
        raise RuntimeError(f"{unit} ComfyUI history did not confirm success")
    latents = list((output / "downloads").rglob("*.safetensors"))
    videos = list((output / "downloads").rglob("*.mp4"))
    if len(latents) != 1 or len(videos) != 1:
        raise RuntimeError(f"{unit} output count: latents={len(latents)} videos={len(videos)}")
    u01_validation = OUTPUT_ROOT / "U01/run/validation.json"
    baseline = json.loads(u01_validation.read_text(encoding="utf-8")) if u01_validation.exists() else None
    expected_temporal = None
    if baseline:
        tensors = {item["name"]: item for item in baseline["latent"]["tensors"]}
        expected_temporal = tensors["video"]["shape"][2]
    report = {
        "unit": unit,
        "gpu_profile": "rtx5090",
        "prompt_id": prompt_id,
        "server_wall_s": server_wall_seconds(history[prompt_id]),
        "latent_output_relative": records[0]["latent_path"],
        "latent": inspect_latent(latents[0], expected_temporal),
        "video": inspect_video(videos[0], unit),
    }
    (output / "validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    make_review_frames(videos[0], output)
    print("CUP_EP01_CHILD_OK", unit, prompt_id, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
