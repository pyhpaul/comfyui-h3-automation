"""Recover the verified U01 AV latent after a post-generation validator error."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from h3_test2_ep01_media import validate_latent_shapes, validate_video_metadata


CONTENT = Path("/content")
RECOVERY = CONTENT / "test2-ep01-u01-recovery.json"
INPUT_MANIFEST = CONTENT / "test2-ep01-input-manifest.json"
OUTPUT = CONTENT / "h3-test2-ep01/U01"
LATENT_ROOT = CONTENT / "h3-rental/ComfyUI/output"
RCLONE = CONTENT / "rclone"
CONFIG = CONTENT / "rclone.conf"
REMOTE_ROOT = "h3drive_h3:comfyui-h3-colab-dedicated/standard-v1/runs/test2-20260925/ep01"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rclone_json(arguments: list[str], rclone: str, config: str) -> dict:
    completed = subprocess.run([rclone, *arguments, "--config", config],
                               capture_output=True, text=True, check=True, timeout=90)
    return json.loads(completed.stdout)


def validate_recovery_manifest(record: dict, input_manifest_sha: str) -> None:
    session = record.get("source_session", "")
    source = f"{REMOTE_ROOT}/{session}/u01/TEST2_U01"
    validation = record.get("validation", {})
    latent = validation.get("latent", {})
    video = validation.get("video", {})
    review = record.get("visual_review", {})
    evidence = review.get("evidence", [])
    expected_evidence = (
        f"{REMOTE_ROOT}/{session}/recovery/U01-contact-sheet.jpg",
        f"{REMOTE_ROOT}/{session}/recovery/U01-last-frame.jpg",
    )
    if (
        record.get("schema_version") != 1
        or record.get("unit") != "U01"
        or not session.startswith("h3-test2-ep01-")
        or record.get("input_manifest_sha256") != input_manifest_sha
        or record.get("source_phase_remote") != f"{source}/phase.json"
        or record.get("source_history_remote") != f"{source}/run/history.json"
        or record.get("latent_remote") != (
            f"{source}/run/downloads/EP01-U01-test2/ep01_u01_00001.safetensors")
        or record.get("video_remote") != (
            f"{source}/run/downloads/EP01-U01-test2/"
            "EP01-U01-test2-pass1_00001-audio.mp4")
        or record.get("source_phase_state") != (
            "failed_after_generation_during_obsolete_latent_shape_gate")
        or review.get("decision") != "continue_with_caveat"
        or not isinstance(evidence, list)
        or any(not isinstance(item, dict) for item in evidence)
        or [item.get("remote") for item in evidence] != list(expected_evidence)
        or any(not item.get("sha256") for item in evidence)
        or validation.get("unit") != "U01"
        or validation.get("gpu_profile") != "rtx5090"
        or validation.get("latent_output_relative") != (
            "h3_context/ep01_u01_00001.safetensors")
        or not validation.get("prompt_id")
        or not latent.get("sha256")
        or not video.get("sha256")
    ):
        raise RuntimeError("U01 recovery manifest is not the approved source")
    validate_latent_shapes(latent["tensors"])
    validate_video_metadata(video["probe"], "U01")


def verify_recovery_sources(record: dict, rclone: str, config: str) -> None:
    validation = record["validation"]
    phase = rclone_json(["cat", record["source_phase_remote"]], rclone, config)
    if (phase.get("session_id") != record["source_session"]
            or phase.get("state") != "failed"
            or phase.get("archive_state") != "verified"
            or phase.get("input_manifest_sha256") != record["input_manifest_sha256"]
            or phase.get("unit") != "U01"):
        raise RuntimeError("U01 original failed phase receipt changed")
    history = rclone_json(["cat", record["source_history_remote"]], rclone, config)
    entry = history.get(validation["prompt_id"], {})
    if entry.get("status", {}).get("status_str") != "success":
        raise RuntimeError("U01 original ComfyUI history does not confirm success")
    with tempfile.TemporaryDirectory(prefix="h3-u01-recovery-") as temporary:
        for name in ("latent", "video"):
            expected = validation[name]
            source = record[f"{name}_remote"]
            remote = rclone_json(["lsjson", source, "--stat", "--hash"],
                                  rclone, config)
            hashes = remote.get("Hashes") or {}
            if (remote.get("Size") != expected["bytes"]
                    or ("sha256" in hashes and hashes["sha256"] != expected["sha256"])):
                raise RuntimeError(f"U01 source {name} hash or size changed")
            print("U01_SOURCE_METADATA", name, "size", remote.get("Size"),
                  "hash_algorithms", sorted(hashes), flush=True)
            if name == "video" and "sha256" not in hashes:
                verify_downloaded_source(source, expected["sha256"],
                                         Path(temporary) / "video", rclone, config)
        for index, item in enumerate(record["visual_review"]["evidence"]):
            source = item["remote"]
            remote = rclone_json(["lsjson", source, "--stat", "--hash"],
                                  rclone, config)
            hashes = remote.get("Hashes") or {}
            if "sha256" in hashes:
                if hashes["sha256"] != item["sha256"]:
                    raise RuntimeError("U01 visual review evidence changed")
            else:
                verify_downloaded_source(source, item["sha256"],
                                         Path(temporary) / f"evidence-{index}",
                                         rclone, config)


def verify_downloaded_source(source: str, expected_sha256: str, destination: Path,
                             rclone: str, config: str) -> None:
    subprocess.run([rclone, "copyto", source, str(destination), "--config", config],
                   check=True, timeout=120)
    if sha256(destination) != expected_sha256:
        raise RuntimeError(f"U01 source {source} downloaded SHA-256 changed")
    print("U01_SOURCE_HASH_VERIFIED", destination.name, expected_sha256, flush=True)


def main() -> None:
    record = json.loads(RECOVERY.read_text(encoding="utf-8"))
    manifest_sha = sha256(INPUT_MANIFEST)
    validate_recovery_manifest(record, manifest_sha)
    verify_recovery_sources(record, str(RCLONE), str(CONFIG))
    if OUTPUT.exists():
        raise RuntimeError("U01 recovery destination already exists")
    relative = record["validation"]["latent_output_relative"]
    destination = (LATENT_ROOT / relative).resolve()
    if not destination.is_relative_to(LATENT_ROOT.resolve()) or destination.exists():
        raise RuntimeError("U01 recovery latent destination is unsafe or occupied")
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(RCLONE), "copyto", record["latent_remote"], str(destination),
                    "--config", str(CONFIG)], check=True, timeout=600)
    expected = record["validation"]["latent"]
    if destination.stat().st_size != expected["bytes"] or sha256(destination) != expected["sha256"]:
        raise RuntimeError("downloaded U01 recovery latent did not match source")
    run = OUTPUT / "run"
    run.mkdir(parents=True)
    (run / "validation.json").write_text(
        json.dumps(record["validation"], indent=2) + "\n", encoding="utf-8")
    phase = {"state": "recovered", "archive_state": "verified", "unit": "U01",
             "label": "TEST2_U01", "session_id": record["source_session"],
             "source_phase_state": "failed", "prompt_id": record["validation"]["prompt_id"],
             "source_phase_remote": record["source_phase_remote"],
             "recovery_manifest_sha256": sha256(RECOVERY)}
    (OUTPUT / "phase.json").write_text(json.dumps(phase, indent=2) + "\n",
                                       encoding="utf-8")
    report = {"state": "ready", "unit": "U01", "source_session": record["source_session"],
              "prompt_id": record["validation"]["prompt_id"],
              "latent_output_relative": relative, "latent_sha256": expected["sha256"],
              "video_sha256": record["validation"]["video"]["sha256"],
              "recovery_manifest_sha256": sha256(RECOVERY)}
    remote = os.environ["H3_TEST2_REMOTE"]
    report_path = CONTENT / "test2-ep01-u01-recovery-report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    subprocess.run([str(RCLONE), "copyto", str(report_path),
                    f"{remote}/recovery-u01.json", "--config", str(CONFIG)],
                   check=True, timeout=120)
    print("TEST2_U01_RECOVERED", json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
