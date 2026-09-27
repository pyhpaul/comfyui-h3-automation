"""Assemble verified Test2 EP01 unit MP4s without another quality-loss encode."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from colab_h3_test2_ep01_host import (
    BACKUP, CONFIG, MANIFEST, REMOTE_ROOT, sha256, unit_remote, verify_unit,
)
from h3_test2_ep01_contract import PARENTS, UNITS


def run(command: list[str], timeout: int = 600, cwd: Path | None = None) -> str:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                               timeout=timeout, check=True)
    return completed.stdout


def remote_stat(path: str) -> dict:
    return json.loads(run(["rclone", "lsjson", path, "--stat", "--hash",
                           "--config", str(CONFIG)], timeout=60))


def video_source(unit: str, validation: dict) -> str:
    root = PurePosixPath(f"/content/h3-test2-ep01/{unit}/run")
    path = PurePosixPath(validation["video"]["path"])
    if (".." in path.parts or not path.is_relative_to(root / "downloads")
            or path.suffix.lower() != ".mp4"):
        raise RuntimeError(f"{unit} validation has an unexpected video path: {path}")
    return str(path.relative_to(root))


def probe(path: Path) -> dict:
    return json.loads(run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames,duration,start_time",
        "-of", "json", str(path),
    ], timeout=90))


def media_summary(media: dict) -> dict:
    streams = media["streams"]
    video = next(item for item in streams if item["codec_type"] == "video")
    audio = next(item for item in streams if item["codec_type"] == "audio")
    if (video["codec_name"] != "h264" or audio["codec_name"] != "aac"
            or (video["width"], video["height"]) != (768, 1376)
            or video["r_frame_rate"] != "24/1"):
        raise RuntimeError("unexpected codec, resolution or frame rate in final MP4")
    return {"duration_s": float(media["format"]["duration"]),
            "video_frames": int(video["nb_frames"]),
            "video_duration_s": float(video["duration"]),
            "audio_duration_s": float(audio["duration"]),
            "av_start_delta_s": abs(float(video["start_time"])
                                    - float(audio["start_time"]))}


def concat_mp4(directory: Path, names: list[str], final: Path) -> None:
    if not names or any(Path(name).name != name or not name.endswith(".mp4") for name in names):
        raise ValueError("concat inputs must be local MP4 basenames")
    list_path = directory / "concat.txt"
    list_path.write_text("".join(f"file '{name}'\n" for name in names), encoding="ascii")
    run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-n",
         "-f", "concat", "-safe", "0", "-i", str(list_path),
         "-map", "0:v:0", "-map", "0:a:0", "-c", "copy",
         "-movflags", "+faststart", str(final)], timeout=900)


def finalize(session: str) -> dict:
    if not session.startswith("h3-test2-ep01-"):
        raise ValueError("unexpected Test2 EP01 session identifier")
    started = time.monotonic()
    directory = BACKUP / "test2-ep01/final" / session
    directory.mkdir(parents=True, exist_ok=True)
    remote = f"{REMOTE_ROOT}/{session}"
    manifest_sha = sha256(MANIFEST)
    entries = []
    parent = None
    for unit in UNITS:
        if PARENTS[unit] is None:
            parent = None
        unit_path = unit_remote(remote, unit)
        validation = verify_unit(unit_path, session, unit, parent, manifest_sha)
        source = f"{unit_path}/TEST2_{unit}/run/{video_source(unit, validation)}"
        expected = validation["video"]
        actual = remote_stat(source)
        if (actual.get("Size") != expected["bytes"]
                or actual.get("Hashes", {}).get("sha256") != expected["sha256"]):
            raise RuntimeError(f"{unit} Drive video differs from verified receipt")
        local = directory / f"{unit}.mp4"
        if not local.exists():
            run(["rclone", "copyto", source, str(local), "--config", str(CONFIG)],
                timeout=600)
        if local.stat().st_size != expected["bytes"] or sha256(local) != expected["sha256"]:
            raise RuntimeError(f"{unit} local video differs from verified receipt")
        entries.append({"unit": unit, "source": source, "file": local.name,
                        "bytes": expected["bytes"], "sha256": expected["sha256"],
                        "duration_s": float(expected["probe"]["format"]["duration"]),
                        "frames": int(next(item for item in expected["probe"]["streams"]
                                           if item["codec_type"] == "video")["nb_frames"]),
                        "prompt_id": validation["prompt_id"]})
        parent = validation["latent_output_relative"]

    final = directory / "EP01-test2-v1.mp4"
    if not final.exists():
        concat_mp4(directory, [item["file"] for item in entries], final)
    result = media_summary(probe(final))
    source_duration = sum(item["duration_s"] for item in entries)
    source_frames = sum(item["frames"] for item in entries)
    if (result["video_frames"] != source_frames
            or abs(result["duration_s"] - source_duration) > 0.5
            or abs(result["video_duration_s"] - result["audio_duration_s"]) > 0.5
            or result["av_start_delta_s"] > 0.05):
        raise RuntimeError(f"final EP01 duration or frame count changed: {result}")
    run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
         "-i", str(final), "-f", "null", "-"], timeout=1200)
    destination = f"{remote}/final/{final.name}"
    try:
        remote_stat(destination)
    except subprocess.CalledProcessError:
        pass
    else:
        raise RuntimeError("final Drive destination already exists; refusing overwrite")
    run(["rclone", "copyto", str(final), destination, "--config", str(CONFIG)],
        timeout=900)
    uploaded = remote_stat(destination)
    final_sha = sha256(final)
    if (uploaded.get("Size") != final.stat().st_size
            or uploaded.get("Hashes", {}).get("sha256") != final_sha):
        raise RuntimeError("final EP01 Drive upload hash mismatch")
    receipt = {"state": "assembled_and_uploaded", "session": session,
               "created_at_utc": datetime.now(timezone.utc).isoformat(),
               "input_manifest_sha256": manifest_sha, "units": entries,
               "assembly": "ffmpeg concat demuxer, stream copy, no second trim",
               "final": {**result, "local": str(final), "remote": destination,
                         "bytes": final.stat().st_size, "sha256": final_sha},
               "wall_s": round(time.monotonic() - started, 2)}
    receipt_path = directory / "final-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    run(["rclone", "copyto", str(receipt_path), f"{remote}/final/final-receipt.json",
         "--config", str(CONFIG)], timeout=120)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True)
    args = parser.parse_args()
    print(json.dumps(finalize(args.session), indent=2), flush=True)


if __name__ == "__main__":
    main()
