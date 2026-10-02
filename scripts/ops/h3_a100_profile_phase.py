"""Run one full-shape H3 sampler step under a reversible profiler hook.

This runs only inside an already-authorized, restored A100 assignment. It
does not allocate a Colab runtime and its result is not a speed sample.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


sys.path.insert(0, "/content")
from h3_a100_profile_hook import install, restore
from h3_a100_attention_probe_hook import install as install_attention
from h3_a100_attention_probe_hook import restore as restore_attention
from h3_a100_ab_phase import (start_comfy, start_telemetry, stop_comfy,
                              verify_attention_mode, verify_memory_mode)
from h3_a100_ab_contract import warmup_graphs_match_except_latent_prefix
from h3_a100_phase_receipt import identity_from_environment, publish_verified


CONTENT = Path("/content")
COMFY = CONTENT / "h3-rental/ComfyUI"
BACKUP = CONTENT / "h3-profile-original"
OUTPUT = CONTENT / "h3-profile-evidence"
REMOTE_PREFIX = ("h3drive_h3:comfyui-h3-colab-dedicated/rental-20260924-5090/"
                 "a100-perf-pilot/profile-")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def backup(remote: str, output: Path) -> None:
    publish_verified(output, remote, Path("/content/rclone"), Path("/content/rclone.conf"))
    print("PROFILE_BACKUP_VERIFIED", remote, flush=True)


def main() -> None:
    remote = os.environ.get("H3_PROFILE_REMOTE", "")
    label = os.environ.get("H3_PROFILE_LABEL", "P_C")
    suffix = remote.removeprefix(REMOTE_PREFIX)
    if not remote.startswith(REMOTE_PREFIX) or not suffix or "/" in suffix:
        raise ValueError("H3_PROFILE_REMOTE must be a unique profile-* prefix")
    if label not in {"P_B", "P_C", "M0"}:
        raise ValueError("H3_PROFILE_LABEL must be P_B, P_C, or M0")
    if not (CONTENT / "h3-a100-ab/preflight.json").is_file():
        raise RuntimeError("frozen-input preflight is missing")
    output = OUTPUT / label
    child = CONTENT / "h3-a100-ab" / label
    backup_dir = BACKUP / label
    attention_backup_dir = BACKUP / f"{label}-attention"
    if output.exists() or child.exists() or backup_dir.exists() or attention_backup_dir.exists():
        raise RuntimeError("profile output or original-source backup already exists")
    output.mkdir(parents=True)
    identity = identity_from_environment(label, CONTENT / "h3-a100-ab/preflight.json")
    result: dict[str, object] = {**vars(identity), "started_at_utc": utc_now(),
                                 "kind": "instrumented_one_step_not_timing_sample"}
    telemetry = None
    telemetry_stream = None
    installed = False
    attention_installed = False
    try:
        stop_comfy()
        result["source_patch"] = install(COMFY, backup_dir)
        installed = True
        result["attention_source_patch"] = install_attention(COMFY, attention_backup_dir)
        attention_installed = True
        if label == "M0":
            os.environ["H3_COMFY_START_SCRIPT"] = "/content/h3_a100_memory_start.sh"
            os.environ["H3_DISABLE_SMART_MEMORY"] = "0"
        start_script = Path(os.environ.get(
            "H3_COMFY_START_SCRIPT", "/content/h3-runner/scripts/ops/comfy_gpu_start.sh"))
        result["startup_sha256"] = hashlib.sha256(start_script.read_bytes()).hexdigest()
        result["disable_smart_memory"] = os.environ.get("H3_DISABLE_SMART_MEMORY", "1")
        os.environ["PYTHONPATH"] = "/content" + os.pathsep + os.environ.get("PYTHONPATH", "")
        os.environ["H3_PROFILE_SAMPLER"] = "1"
        os.environ["H3_PROFILE_OUTPUT"] = str(output / "sampler-profile.json")
        os.environ["H3_PROFILE_TIMELINE_OUTPUT"] = str(output / "sampler-timeline.json.gz")
        os.environ["H3_A100_ATTENTION_PROBE"] = "1"
        os.environ["H3_ATTENTION_PROBE_OUTPUT"] = str(output)
        start_comfy(output / "comfyUI.log")
        telemetry, telemetry_stream = start_telemetry(output / "nvidia-smi.csv")
        env = os.environ.copy()
        env["H3_AB_RUN"] = label
        with (output / "runner.log").open("w") as stream:
            subprocess.run([str(COMFY / ".venv/bin/python"),
                            "/content/h3_a100_ab_child.py"], cwd="/content/h3-runner",
                           env=env, stdout=stream, stderr=subprocess.STDOUT,
                           check=True, timeout=600)
        verify_attention_mode(label, output / "comfyUI.log")
        verify_memory_mode("M0" if label == "M0" else "S0", output / "comfyUI.log")
        if not (output / "sampler-profile.json").is_file():
            raise RuntimeError("sampler profiler report is missing")
        if label in {"P_C", "M0"} and not (output / "attention-calls.jsonl").is_file():
            raise RuntimeError("H3 attention metadata is missing")
        if label == "M0":
            prior = CONTENT / "h3-a100-ab/P_C/submitted_graph.json"
            current = child / "submitted_graph.json"
            if not warmup_graphs_match_except_latent_prefix(
                    json.loads(prior.read_text()), json.loads(current.read_text())):
                raise RuntimeError("M0 warmup graph differs from P_C beyond the latent prefix")
        shutil.copytree(child, output / "child")
        shutil.copy2(CONTENT / "h3-a100-ab/preflight.json", output / "preflight.json")
        result["state"] = "success"
    except Exception as exc:
        result["state"] = "failed"
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if telemetry is not None:
            telemetry.terminate()
            try:
                telemetry.wait(timeout=5)
            except subprocess.TimeoutExpired:
                telemetry.kill()
                telemetry.wait(timeout=5)
        if telemetry_stream is not None:
            telemetry_stream.close()
        try:
            stop_comfy()
        except RuntimeError as exc:
            result["state"] = "failed"
            result["stop_error"] = str(exc)
        if installed:
            try:
                restore(COMFY, backup_dir)
                shutil.copy2(backup_dir / "manifest.json", output / "source-patch.json")
            except (OSError, RuntimeError) as exc:
                result["state"] = "failed"
                result["restore_error"] = str(exc)
        if attention_installed:
            try:
                restore_attention(COMFY, attention_backup_dir)
                shutil.copy2(attention_backup_dir / "manifest.json",
                             output / "attention-source-patch.json")
            except (OSError, RuntimeError) as exc:
                result["state"] = "failed"
                result["attention_restore_error"] = str(exc)
        result["finished_at_utc"] = utc_now()
        (output / "phase.json").write_text(json.dumps(result, indent=2) + "\n")
        backup(f"{remote}/{label}", output)
    print("PROFILE_PHASE_RESULT", json.dumps(result), flush=True)
    if result["state"] != "success":
        raise RuntimeError("instrumented one-step profile failed")


if __name__ == "__main__":
    main()
