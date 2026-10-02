"""Submit and validate exactly one frozen Test2 EP02/EP03 G4 prompt."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

import yaml


RUNNER = Path("/content/h3-runner")
sys.path[:0] = [str(RUNNER / "src"), str(RUNNER / "scripts"), "/content"]

import run_ep_units_profiled as runner
from comfy_orch.client import ComfyClient
from h3_a100_media import decoded_stream_sha256
from h3_test2_ep01_media import inspect_latent
from h3_test2_ep23_contract import FPS, job_name, parent_unit, validate_graph, validate_job


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def server_wall_seconds(entry: dict) -> float:
    stamps = {name: details["timestamp"] for name, details in entry["status"]["messages"]
              if name in {"execution_start", "execution_success"}}
    if set(stamps) != {"execution_start", "execution_success"}:
        raise RuntimeError("missing ComfyUI execution start/success timestamps")
    return round((stamps["execution_success"] - stamps["execution_start"]) / 1000, 3)


def inspect_video(path: Path, parent: str | None) -> dict:
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-show_entries", "stream=index,codec_type,codec_name,width,height,r_frame_rate,nb_frames,duration,start_time",
        "-of", "json", str(path),
    ], capture_output=True, text=True, timeout=60, check=True)
    media = json.loads(probe.stdout)
    video = next((item for item in media["streams"] if item.get("codec_type") == "video"), None)
    audio = next((item for item in media["streams"] if item.get("codec_type") == "audio"), None)
    expected_frames = 362 - (22 if parent else 0)
    expected_duration = expected_frames / FPS
    if (
        not video or not audio
        or video.get("codec_name") != "h264" or audio.get("codec_name") != "aac"
        or (video.get("width"), video.get("height")) != (768, 1376)
        or video.get("r_frame_rate") != "24/1"
        or int(video.get("nb_frames", 0)) != expected_frames
        or abs(float(media["format"]["duration"]) - expected_duration) > 0.05
        or abs(float(video["duration"]) - expected_duration) > 0.05
        or abs(float(video["duration"]) - float(audio["duration"])) > 0.05
        or abs(float(video["start_time"]) - float(audio["start_time"])) > 0.05
    ):
        raise RuntimeError(f"unexpected Test2 G4 media metadata: {media}")
    audio_probe = subprocess.run([
        "ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-i", str(path),
        "-vn", "-af", "volumedetect", "-f", "null", "-",
    ], capture_output=True, text=True, timeout=60, check=True)
    match = re.search(r"max_volume:\s*([\d.-]+) dB", audio_probe.stderr)
    if not match or float(match.group(1)) < -60:
        raise RuntimeError("Test2 G4 audio is silent or unexpectedly quiet")
    return {
        "path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path),
        "probe": media, "audio_max_db": float(match.group(1)),
        "decoded_video_sha256": decoded_stream_sha256(path, "video"),
        "decoded_audio_sha256": decoded_stream_sha256(path, "audio"),
    }


def review_frames(video: Path, output: Path, parent: str | None) -> None:
    subprocess.run([
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video), "-vf", "fps=1/3,scale=384:-1,tile=3x2",
        "-frames:v", "1", str(output / "contact-sheet.jpg"),
    ], check=True, timeout=90)
    last_second = "13.6" if parent else "14.5"
    for label, second in (("first", "0.5"), ("last", last_second)):
        subprocess.run([
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", second, "-i", str(video), "-frames:v", "1",
            str(output / f"{label}-frame.jpg"),
        ], check=True, timeout=90)


def run_one(episode: str, unit: str, parent_path: str | None, output: Path) -> dict:
    job = RUNNER / "jobs/ep_units" / job_name(episode, unit)
    raw = yaml.safe_load((job / "job.yaml").read_text(encoding="utf-8"))
    validate_job(raw, episode, unit)
    refs = [key for key in raw["fields"] if key.startswith("ref_image_")]
    run_output = output / "run"
    run_output.mkdir(exist_ok=False)
    original_queue = ComfyClient.queue_prompt
    submitted = 0

    def queue(client: ComfyClient, workflow: dict) -> str:
        nonlocal submitted
        if submitted:
            raise RuntimeError("only one prompt is permitted per Test2 unit attempt")
        validate_graph(workflow, episode, unit, parent_path, len(refs))
        (run_output / "submitted_graph.json").write_text(
            json.dumps(workflow, indent=2) + "\n", encoding="utf-8")
        submitted += 1
        prompt_id = original_queue(client, workflow)
        (run_output / "prompt-id.txt").write_text(prompt_id + "\n", encoding="utf-8")
        return prompt_id

    ComfyClient.queue_prompt = queue
    os.environ["COMFY_BASE_URL"] = "http://127.0.0.1:8188"
    os.environ.pop("H3_LATENT_SUFFIX", None)
    sys.argv = [
        "h3_test2_ep23_child.py", "--units", unit, "--job-glob", job_name(episode, unit),
        "--continuity", "motion_latent", "--gpu-profile", "rtx5090",
        "--download-dir", str(run_output / "downloads"),
        "--batch-log", str(run_output / "batch.json"),
    ]
    if parent_path:
        sys.argv.extend(("--parent-latent", parent_path))
    status = runner.main()
    if status:
        raise RuntimeError(f"Test2 runner exited {status}")
    records = json.loads((run_output / "batch.json").read_text(encoding="utf-8"))
    if submitted != 1 or len(records) != 1 or records[0].get("state") != "done":
        raise RuntimeError("expected exactly one completed Test2 prompt")
    prompt_id = records[0]["prompt_id"]
    with urlopen(f"http://127.0.0.1:8188/history/{prompt_id}", timeout=20) as response:
        history = json.load(response)
    (run_output / "history.json").write_text(
        json.dumps(history, indent=2) + "\n", encoding="utf-8")
    if history[prompt_id].get("status", {}).get("status_str") != "success":
        raise RuntimeError("ComfyUI history did not confirm success")
    latents = list((run_output / "downloads").rglob("*.safetensors"))
    videos = list((run_output / "downloads").rglob("*.mp4"))
    if len(latents) != 1 or len(videos) != 1:
        raise RuntimeError(f"output count: latents={len(latents)} videos={len(videos)}")
    report = {
        "episode": episode, "unit": unit, "parent_unit": parent_unit(episode, unit),
        "gpu_profile": "rtx5090", "prompt_id": prompt_id,
        "server_wall_s": server_wall_seconds(history[prompt_id]),
        "latent_output_relative": records[0]["latent_path"],
        "latent": inspect_latent(latents[0]),
        "video": inspect_video(videos[0], parent_unit(episode, unit)),
    }
    (run_output / "validation.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")
    review_frames(videos[0], run_output, parent_unit(episode, unit))
    return report


def main() -> None:
    episode = os.environ["H3_TEST2_EPISODE"]
    unit = os.environ["H3_TEST2_UNIT"]
    parent_path = os.environ.get("H3_TEST2_PARENT_LATENT") or None
    output = Path(os.environ["H3_TEST2_ATTEMPT_DIR"])
    report = run_one(episode, unit, parent_path, output)
    print("TEST2_EP23_CHILD_OK", episode, unit, report["prompt_id"], flush=True)


if __name__ == "__main__":
    main()
