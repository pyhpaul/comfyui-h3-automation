"""Assemble verified Test2 EP02/EP03 MP4s after the paid G4 assignment stops."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from h3_test2_ep23_contract import UNITS, parent_unit
from h3_test2_ep01_finalize import concat_mp4, media_summary, probe, run, sha256


BACKUP = Path("/mnt/d/comfyui-h3-backups/rental-20260924-5090")
CONFIG = Path.home() / ".config/rclone-h3/rclone.conf"
MANIFEST = Path(__file__).resolve().parents[2] / "docs/ops/drive-test2-ep02-ep03-v1.json"
REMOTE_ROOT = "h3drive_h3:comfyui-h3-colab-dedicated/standard-v1/runs/test2-20260925/ep02-ep03"


def remote_json(path: str) -> dict:
    return json.loads(run(["rclone", "cat", path, "--config", str(CONFIG)], timeout=60))


def remote_stat(path: str) -> dict:
    return json.loads(run(["rclone", "lsjson", path, "--stat", "--hash",
                           "--config", str(CONFIG)], timeout=60))


def attempt_dirs(remote: str) -> list[str]:
    output = run(["rclone", "lsf", remote, "--dirs-only", "--config", str(CONFIG)],
                 timeout=60)
    return [line.rstrip("/") for line in output.splitlines() if line.strip()]


def selected_attempt(remote: str, session: str, episode: str, unit: str,
                     manifest_sha: str, expected_parent: str | None) -> tuple[str, dict]:
    successes = []
    for attempt in attempt_dirs(remote):
        prefix = f"{remote}/{attempt}"
        receipt = remote_json(f"{prefix}/phase.json")
        if receipt.get("state") != "success":
            continue
        if (
            receipt.get("archive_state") != "verified"
            or receipt.get("session_id") != session
            or receipt.get("label") != f"{episode}_{unit}"
            or receipt.get("episode") != episode
            or receipt.get("unit") != unit
            or receipt.get("parent_latent") != expected_parent
            or receipt.get("input_manifest_sha256") != manifest_sha
        ):
            raise RuntimeError(f"{episode} {unit} success receipt has wrong identity")
        successes.append((prefix, remote_json(f"{prefix}/run/validation.json")))
    if len(successes) != 1:
        raise RuntimeError(f"{episode} {unit} expected one verified success, found {len(successes)}")
    return successes[0]


def video_remote(prefix: str, episode: str, unit: str, validation: dict) -> str:
    attempt = PurePosixPath(prefix).name
    root = PurePosixPath(f"/content/h3-test2-ep23/{episode}/{unit}/{attempt}/run")
    video = PurePosixPath(validation["video"]["path"])
    if ".." in video.parts or not video.is_relative_to(root / "downloads"):
        raise RuntimeError(f"{episode} {unit} validation video path escaped attempt")
    if video.suffix.lower() != ".mp4":
        raise RuntimeError(f"{episode} {unit} validation video is not MP4")
    return f"{prefix}/run/{video.relative_to(root)}"


def verified_video(source: str, local: Path, expected: dict) -> None:
    remote = remote_stat(source)
    if remote.get("Size") != expected["bytes"]:
        raise RuntimeError(f"Drive video size changed: {source}")
    remote_hashes = remote.get("Hashes") or {}
    if remote_hashes.get("sha256") and remote_hashes["sha256"] != expected["sha256"]:
        raise RuntimeError(f"Drive video SHA-256 changed: {source}")
    if not local.exists():
        run(["rclone", "copyto", source, str(local), "--config", str(CONFIG)], timeout=600)
    if local.stat().st_size != expected["bytes"] or sha256(local) != expected["sha256"]:
        raise RuntimeError(f"downloaded video differs from verified receipt: {source}")
    if remote_hashes.get("md5"):
        local_md5 = hashlib.md5(local.read_bytes()).hexdigest()
        if local_md5 != remote_hashes["md5"]:
            raise RuntimeError(f"Drive video MD5 changed: {source}")


def finalize_episode(session: str, episode: str) -> dict:
    if episode not in UNITS or not session.startswith("h3-test2-ep23-"):
        raise ValueError("unexpected Test2 episode or session")
    started = time.monotonic()
    remote = f"{REMOTE_ROOT}/{session}"
    directory = BACKUP / "test2-ep02-ep03/final" / session / episode
    directory.mkdir(parents=True, exist_ok=True)
    manifest_sha = sha256(MANIFEST)
    entries = []
    previous_latent = None
    for unit in UNITS[episode]:
        parent = parent_unit(episode, unit)
        expected_parent = previous_latent if parent else None
        prefix, validation = selected_attempt(
            f"{remote}/{episode}_{unit}", session, episode, unit,
            manifest_sha, expected_parent)
        if validation.get("episode") != episode or validation.get("unit") != unit:
            raise RuntimeError(f"{episode} {unit} validation identity mismatch")
        if validation.get("parent_unit") != parent:
            raise RuntimeError(f"{episode} {unit} validation topology mismatch")
        source = video_remote(prefix, episode, unit, validation)
        local = directory / f"{unit}.mp4"
        verified_video(source, local, validation["video"])
        video_stream = next(item for item in validation["video"]["probe"]["streams"]
                            if item["codec_type"] == "video")
        entries.append({
            "unit": unit, "attempt_remote": prefix, "source": source,
            "file": local.name, "bytes": local.stat().st_size,
            "sha256": validation["video"]["sha256"],
            "frames": int(video_stream["nb_frames"]),
            "duration_s": float(validation["video"]["probe"]["format"]["duration"]),
            "prompt_id": validation["prompt_id"],
        })
        previous_latent = validation["latent_output_relative"]
    version = "v2" if episode == "EP02" else "v1"
    final = directory / f"{episode}-test2-{version}.mp4"
    if not final.exists():
        concat_mp4(directory, [entry["file"] for entry in entries], final)
    summary = media_summary(probe(final))
    expected_frames = sum(entry["frames"] for entry in entries)
    expected_duration = sum(entry["duration_s"] for entry in entries)
    if (
        summary["video_frames"] != expected_frames
        or abs(summary["duration_s"] - expected_duration) > 0.5
        or abs(summary["video_duration_s"] - summary["audio_duration_s"]) > 0.5
        or summary["av_start_delta_s"] > 0.05
    ):
        raise RuntimeError(f"{episode} final stream-copy result differs: {summary}")
    run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
         "-i", str(final), "-f", "null", "-"], timeout=1200)
    destination = f"{remote}/final/{final.name}"
    try:
        remote_stat(destination)
    except subprocess.CalledProcessError:
        pass
    else:
        raise RuntimeError("Drive final destination exists; refusing overwrite")
    run(["rclone", "copyto", str(final), destination, "--config", str(CONFIG)], timeout=900)
    uploaded = remote_stat(destination)
    final_sha = sha256(final)
    if uploaded.get("Size") != final.stat().st_size:
        raise RuntimeError("Drive final size changed after upload")
    if uploaded.get("Hashes", {}).get("sha256") not in {None, final_sha}:
        raise RuntimeError("Drive final SHA-256 changed after upload")
    if uploaded.get("Hashes", {}).get("md5") != hashlib.md5(final.read_bytes()).hexdigest():
        raise RuntimeError("Drive final MD5 changed after upload")
    receipt = {
        "state": "assembled_and_uploaded", "session": session, "episode": episode,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_manifest_sha256": manifest_sha, "units": entries,
        "assembly": "ffmpeg concat demuxer, stream copy, no second trim",
        "final": {**summary, "local": str(final), "remote": destination,
                  "bytes": final.stat().st_size, "sha256": final_sha},
        "wall_s": round(time.monotonic() - started, 2),
    }
    receipt_path = directory / "final-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    run(["rclone", "copyto", str(receipt_path),
         f"{remote}/final/{episode}-final-receipt.json", "--config", str(CONFIG)], timeout=120)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True)
    parser.add_argument("--episode", choices=tuple(UNITS), required=True)
    args = parser.parse_args()
    print(json.dumps(finalize_episode(args.session, args.episode), indent=2), flush=True)


if __name__ == "__main__":
    main()
