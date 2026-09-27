"""Run one frozen U02 A100 attention sample inside the restored Colab venv."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

import torch
from safetensors import safe_open


RUNNER = Path("/content/h3-runner")
sys.path.insert(0, str(RUNNER / "src"))
sys.path.insert(0, str(RUNNER / "scripts"))
sys.path.insert(0, "/content")

import run_ep_units_profiled as runner
from comfy_orch.client import ComfyClient
from h3_a100_ab_contract import (FORMAL_RUNS, MEMORY_FORMAL_RUNS, PREWARM_RUNS,
                                  RUN_PROFILES, graphs_match_except_candidate,
                                  graphs_match_except_output_prefix)
from h3_a100_media import decoded_stream_sha256


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def inspect_latent(path: Path) -> dict:
    expected_shapes = {"audio": [1, 32, 2, 547], "video": [1, 24, 97, 86, 48]}
    tensors = []
    with safe_open(path, framework="pt", device="cpu") as opened:
        for name in opened.keys():
            tensor = opened.get_tensor(name)
            finite = bool(torch.isfinite(tensor).all().item())
            tensors.append({"name": name, "shape": list(tensor.shape),
                            "dtype": str(tensor.dtype), "finite": finite})
    if ({item["name"]: item["shape"] for item in tensors} != expected_shapes
            or not all(item["finite"] and item["dtype"] == "torch.float32" for item in tensors)):
        raise RuntimeError("AV latent shape, dtype, or finite check failed")
    return {"path": str(path), "bytes": path.stat().st_size,
            "sha256": sha256(path), "tensors": tensors}


def inspect_video(path: Path) -> dict:
    command = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-show_entries", "stream=index,codec_type,codec_name,width,height,r_frame_rate,nb_frames,duration,start_time",
               "-of", "json", str(path)]
    probe = subprocess.run(command, capture_output=True, text=True, timeout=60, check=True)
    media = json.loads(probe.stdout)
    video = next((item for item in media["streams"] if item["codec_type"] == "video"), None)
    audio = next((item for item in media["streams"] if item["codec_type"] == "audio"), None)
    duration = float(media["format"]["duration"])
    if (not video or not audio or video.get("codec_name") != "h264"
            or video.get("width") != 768 or video.get("height") != 1376
            or video.get("r_frame_rate") != "24/1" or video.get("nb_frames") != "306"
            or not 12.7 <= duration <= 12.8
            or abs(float(video["duration"]) - float(audio["duration"])) > 0.05
            or abs(float(video["start_time"]) - float(audio["start_time"])) > 0.05):
        raise RuntimeError(f"unexpected U02 media metadata: {media}")
    audio_probe = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-nostats",
                                  "-i", str(path), "-vn", "-af", "volumedetect",
                                  "-f", "null", "-"], capture_output=True, text=True,
                                 timeout=60, check=True)
    match = re.search(r"max_volume:\s*([\d.-]+) dB", audio_probe.stderr)
    if not match or float(match.group(1)) < -60:
        raise RuntimeError("U02 audio is silent or unexpectedly quiet")
    return {"path": str(path), "bytes": path.stat().st_size,
            "sha256": sha256(path), "probe": media, "audio_max_db": float(match.group(1)),
            "decoded_video_sha256": decoded_stream_sha256(path, "video"),
            "decoded_audio_sha256": decoded_stream_sha256(path, "audio")}


def assert_graph_contract(label: str, graph: dict) -> None:
    if label in MEMORY_FORMAL_RUNS:
        if label == "S1":
            return
        baseline = Path("/content/h3-a100-ab/S1/submitted_graph.json")
        matches = graphs_match_except_output_prefix
    elif label in FORMAL_RUNS and label != "B1":
        baseline = Path("/content/h3-a100-ab/B1/submitted_graph.json")
        matches = graphs_match_except_candidate
    else:
        return
    if not baseline.is_file():
        raise RuntimeError(f"{baseline.parent.name} graph is missing; cannot validate graph parity")
    if not matches(json.loads(baseline.read_text()), graph):
        raise RuntimeError(f"{label} graph differs from {baseline.parent.name} beyond approved changes")


def server_wall_seconds(entry: dict) -> float:
    stamps = {name: details["timestamp"] for name, details in entry["status"]["messages"]
              if name in {"execution_start", "execution_success"}}
    if set(stamps) != {"execution_start", "execution_success"}:
        raise RuntimeError("missing ComfyUI execution start/success timestamps")
    return round((stamps["execution_success"] - stamps["execution_start"]) / 1000, 3)


def main() -> int:
    label = os.environ.get("H3_AB_RUN", "")
    if label not in RUN_PROFILES:
        raise ValueError(f"H3_AB_RUN must be one of {sorted(RUN_PROFILES)}")
    output = Path("/content/h3-a100-ab") / label
    output.mkdir(parents=True, exist_ok=True)
    warmup = label in PREWARM_RUNS
    original_queue = ComfyClient.queue_prompt

    def queue(self: ComfyClient, workflow: dict) -> str:
        graph = copy.deepcopy(workflow)
        graph["264"]["inputs"]["filename_prefix"] += f"-ab-{label.lower()}"
        if warmup:
            graph["289"]["inputs"]["step"] = 1
            graph.pop("264")
        else:
            assert_graph_contract(label, graph)
        (output / "submitted_graph.json").write_text(json.dumps(graph, indent=2) + "\n")
        return original_queue(self, graph)

    ComfyClient.queue_prompt = queue
    os.environ["COMFY_BASE_URL"] = "http://127.0.0.1:8188"
    os.environ["H3_LATENT_SUFFIX"] = f"ab_{label.lower()}"
    sys.argv = [sys.argv[0], "--units", "U02", "--job-glob", "EP04-H3-manual-v16-{unit}",
                "--continuity", "motion_latent", "--parent-latent",
                "h3_context/ep04_u01_00001.safetensors", "--gpu-profile", RUN_PROFILES[label],
                "--download-dir", str(output / "downloads"),
                "--batch-log", str(output / "batch.json")]
    status = runner.main()
    if status:
        return status
    records = json.loads((output / "batch.json").read_text())
    if len(records) != 1 or records[0]["state"] != "done":
        raise RuntimeError("expected exactly one completed U02 record")
    prompt_id = records[0]["prompt_id"]
    with urlopen(f"http://127.0.0.1:8188/history/{prompt_id}", timeout=20) as response:
        history = json.load(response)
    (output / "history.json").write_text(json.dumps(history, indent=2) + "\n")
    if history[prompt_id].get("status", {}).get("status_str") != "success":
        raise RuntimeError("ComfyUI history did not confirm success")
    latents = list((output / "downloads").rglob("*.safetensors"))
    videos = list((output / "downloads").rglob("*.mp4"))
    if len(latents) != 1 or (not warmup and len(videos) != 1) or (warmup and videos):
        raise RuntimeError(f"unexpected output count: latents={len(latents)} videos={len(videos)}")
    report = {"label": label, "profile": RUN_PROFILES[label], "prompt_id": prompt_id,
              "warmup": warmup, "server_wall_s": server_wall_seconds(history[prompt_id]),
              "latent": inspect_latent(latents[0])}
    if not warmup:
        report["video"] = inspect_video(videos[0])
    (output / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print("AB_CHILD_OK", label, prompt_id, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
