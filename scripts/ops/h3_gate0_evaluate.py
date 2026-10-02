"""Read-only Gate 0 decision from one run's raw, hash-bound artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from h3_cross_gpu_gate0 import compare_graphs, sha256_file
from h3_gate0_outputs import AudioContract, history_output_paths, inspect_latent, inspect_video
from h3_gate0_progress import evaluate_progress
from h3_gate0_receipt import derive_history
from h3_gate0_telemetry import verify_telemetry
from h3_gate0_handoff import SHA256, valid_endpoint


FROZEN_MANIFEST_SHA256 = "9a5f0d43b7e93a0fc5a3226c1970f79e88db03550cfc57dbbdcb502c5beb4609"
APPROVED_AUDIO_ADDENDUM_SHA256 = "949677963c5453c4924b9fbaef2cd49fa7063af631d2afe614c3e42ed6f89f52"
C1_VALIDATION_SHA256 = "8e4bad0f05c15f062180f5cf990a1b75277b07d86be94b27ac134ea4eb6d5ee4"
C1_VIDEO_SHA256 = "f7d9898aa135548bc5448524daf6fe893398c80411fe42db7bfe72153a8a4971"
C1_AUDIO_EVIDENCE_SHA256 = "c1235fa6115b0076dc9d2fd9bcc814ef90b27af8773721cb940f9be2a3e83f12"
REQUIRED_DERIVED = ("graph_parent", "history", "handoff",
                    "observer_handshake", "assets", "media", "telemetry")


@dataclass(frozen=True)
class EvidenceFiles:
    run_id: str
    prompt_id: str
    profile: str
    manifest: Path
    reference_graph: Path
    submitted_graph: Path
    history: Path
    parent: Path
    expected_manifest_sha256: str = FROZEN_MANIFEST_SHA256
    output_root: Path | None = None
    comfy_root: Path | None = None
    runner_root: Path | None = None
    ready: Path | None = None
    attempt: Path | None = None
    prompt_file: Path | None = None
    trace: Path | None = None
    video_baseline: Path | None = None
    latent_baseline: Path | None = None
    telemetry: Path | None = None
    environment: Path | None = None
    audio_addendum: Path | None = None


def decide(checks: dict[str, dict[str, Any]]) -> str:
    """Contradiction wins; an unknown WS only downgrades a valid screen."""
    if any(item.get("tier") == "INCOMPARABLE" for item in checks.values()):
        return "INCOMPARABLE"
    if any(checks.get(name, {}).get("tier") != "derived_verified"
           for name in REQUIRED_DERIVED) \
            or checks.get("environment", {}).get("tier") != "reported_only" \
            or checks.get("candidate_profile", {}).get("tier") != "reported_only":
        return "HISTORY_ONLY_NOT_SCREEN"
    return ("deployment_combination_screen"
            if checks.get("ws", {}).get("tier") == "derived_verified"
            else "server_wall_screen_sampler_unknown")


def _read_json(path: Path, hashes: dict[str, str], label: str) -> Any:
    raw = path.read_bytes()
    hashes[label] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw)


def _check_graph(spec: EvidenceFiles, hashes: dict[str, str]) -> tuple[dict, dict, dict]:
    manifest = _read_json(spec.manifest, hashes, "manifest")
    if hashes["manifest"] != spec.expected_manifest_sha256:
        raise ValueError("frozen manifest SHA-256 differs")
    reference = _read_json(spec.reference_graph, hashes, "reference_graph")
    candidate = _read_json(spec.submitted_graph, hashes, "submitted_graph")
    if hashes["reference_graph"] != manifest["reference_graph_sha256"]:
        raise ValueError("reference graph differs from frozen manifest")
    compare_graphs(manifest, reference, candidate, spec.profile,
                   spec.parent, spec.output_root,
                   spec.comfy_root / "input" if spec.comfy_root else None,
                   spec.run_id)
    hashes["parent"] = sha256_file(spec.parent)
    return manifest, reference, candidate


def _audit_assets(manifest: dict, spec: EvidenceFiles,
                  hashes: dict[str, str]) -> dict[str, str]:
    if spec.comfy_root is None or spec.runner_root is None:
        raise FileNotFoundError("source-side ComfyUI and runner roots are missing")
    source_hashes: dict[str, str] = {}
    approvals = manifest.get("approved_source_deltas", {})
    for item in manifest["assets"]:
        logical = item["path"]
        if logical.startswith("ComfyUI/"):
            path = spec.comfy_root / logical.removeprefix("ComfyUI/")
        elif logical.startswith("runner/"):
            path = spec.runner_root / logical.removeprefix("runner/")
        else:
            raise ValueError(f"asset path is outside approved roots: {logical}")
        if not path.is_file():
            raise ValueError(f"required asset is missing: {logical}")
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(
                (spec.comfy_root if logical.startswith("ComfyUI/")
                 else spec.runner_root).resolve(strict=True)):
            raise ValueError(f"asset path is symlink redirected: {logical}")
        digest = sha256_file(path)
        size = path.stat().st_size
        hashes[f"asset:{logical}"] = digest
        if (digest, size) != (item["sha256"], item["bytes"]):
            allowed = item["kind"] == "source" and any(
                record.get("sha256") == digest and record.get("bytes") == size
                and isinstance(record.get("review_id"), str) and record["review_id"].strip()
                for record in approvals.get(logical, []))
            if not allowed:
                raise ValueError(f"asset hash or size differs: {logical}")
        if item["kind"] == "source":
            source_hashes[logical] = digest
    return source_hashes


def _handoff(spec: EvidenceFiles, history_info: dict,
             hashes: dict[str, str]) -> dict[str, Any]:
    if spec.ready is None or spec.attempt is None or spec.prompt_file is None:
        raise FileNotFoundError("one-shot handoff files are missing")
    if spec.ready.name != "ready.json" or spec.attempt.name != "attempt.json" \
            or spec.prompt_file.name != "prompt.json" \
            or not spec.ready.parent == spec.attempt.parent == spec.prompt_file.parent \
            or spec.ready.parent.name != spec.run_id \
            or any(path.is_symlink() for path in
                   (spec.ready, spec.attempt, spec.prompt_file)):
        raise ValueError("handoff files are outside the canonical run namespace")
    ready = _read_json(spec.ready, hashes, "ready")
    attempt = _read_json(spec.attempt, hashes, "attempt")
    published = _read_json(spec.prompt_file, hashes, "prompt_file")
    graph_sha = hashes["submitted_graph"]
    client_id = history_info["client_id"]
    endpoint = ready.get("endpoint")
    attempt_id = attempt.get("attempt_id")
    try:
        valid_ids = (isinstance(client_id, str) and str(uuid.UUID(client_id)) == client_id
                     and isinstance(attempt_id, str)
                     and str(uuid.UUID(attempt_id)) == attempt_id)
    except ValueError:
        valid_ids = False
    if not client_id or ready.get("observer_state") != "connected" \
            or not valid_ids or not valid_endpoint(endpoint) \
            or isinstance(ready.get("observer_pid"), bool) \
            or not isinstance(ready.get("observer_pid"), int) \
            or ready["observer_pid"] <= 0 \
            or ready.get("run_id") != spec.run_id or ready.get("graph_sha256") != graph_sha \
            or ready.get("client_id") != client_id \
            or attempt.get("run_id") != spec.run_id or attempt.get("graph_sha256") != graph_sha \
            or attempt.get("endpoint") != endpoint \
            or attempt.get("client_id") != client_id \
            or attempt.get("state") != "transport_may_have_started" \
            or published.get("run_id") != spec.run_id \
            or published.get("graph_sha256") != graph_sha \
            or published.get("endpoint") != endpoint \
            or published.get("prompt_id") != spec.prompt_id \
            or published.get("client_id") != client_id \
            or published.get("attempt_id") != attempt_id:
        raise ValueError("handoff does not bind this run, graph, client and prompt")
    ready_at = datetime.fromisoformat(ready["ready_at_utc"])
    claimed_at = datetime.fromisoformat(attempt["claimed_at_utc"])
    published_at = datetime.fromisoformat(published["published_at_utc"])
    if any(value.tzinfo is None for value in (ready_at, claimed_at, published_at)) \
            or not ready_at <= claimed_at <= published_at \
            or (claimed_at - ready_at).total_seconds() > 30 \
            or claimed_at > datetime.fromisoformat(history_info["started_at_utc"]) \
            or claimed_at > datetime.fromisoformat(history_info["finished_at_utc"]):
        raise ValueError("handoff timestamps are not causal")
    return {"client_id": client_id, "endpoint": endpoint,
            "ready_at_utc": ready["ready_at_utc"],
            "claimed_at_utc": attempt["claimed_at_utc"],
            "attempt_id": attempt_id}


def _environment(spec: EvidenceFiles, history_info: dict,
                 source_hashes: dict[str, str], hashes: dict[str, str],
                 handoff: dict[str, Any] | None) -> dict[str, Any]:
    if spec.environment is None:
        raise FileNotFoundError("run environment capture is missing")
    env = _read_json(spec.environment, hashes, "environment")
    start = datetime.fromisoformat(history_info["started_at_utc"])
    process_start = datetime.fromisoformat(env["process_started_at_utc"])
    if process_start.tzinfo is None or process_start >= start \
            or env.get("run_id") != spec.run_id \
            or env.get("graph_sha256") != hashes["submitted_graph"] \
            or env.get("client_id") != history_info["client_id"] \
            or env.get("source_hashes") != source_hashes \
            or (handoff is not None and env.get("endpoint") != handoff["endpoint"]) \
            or env.get("comfy_root") != str(spec.comfy_root.resolve(strict=True)) \
            or env.get("input_root") != str((spec.comfy_root / "input").resolve(strict=True)) \
            or spec.output_root.resolve(strict=True) != (spec.comfy_root / "output").resolve(strict=True) \
            or env.get("runner_root") != str(spec.runner_root.resolve(strict=True)) \
            or isinstance(env.get("process_pid"), bool) \
            or not isinstance(env.get("process_pid"), int) or env["process_pid"] <= 0 \
            or not isinstance(env.get("gpu_uuid"), str) or not env["gpu_uuid"] \
            or isinstance(env.get("device_index"), bool) \
            or not isinstance(env.get("device_index"), int) or env["device_index"] < 0 \
            or any(not env.get(key) for key in ("driver", "comfyui", "torch", "cuda",
                                                "python")) \
            or not isinstance(env.get("startup_flags"), str) \
            or not env["startup_flags"].strip():
        raise ValueError("environment and deployed source identity differ")
    if "--input-directory" in env["startup_flags"] or "--output-directory" in env["startup_flags"]:
        raise ValueError("alternate ComfyUI input or output directory is not admitted")
    gpu_name = env.get("gpu_name")
    queue = env.get("queue_state")
    binary_path = env.get("sage_binary_path")
    binary_sha = env.get("sage_binary_sha256")
    if not isinstance(gpu_name, str) \
            or re.fullmatch(r"(?:NVIDIA )?GeForce RTX 5090", gpu_name.strip(), re.I) is None \
            or env.get("compute_capability") != "12.0" \
            or env.get("profile") != "rtx5090" \
            or not isinstance(queue, dict) \
            or queue.get("prompt_id") != spec.prompt_id \
            or isinstance(queue.get("active_prompt_count"), bool) \
            or queue.get("active_prompt_count") != 1 \
            or queue.get("sampler_cached") is not False \
            or not isinstance(binary_path, str) or not Path(binary_path).is_absolute() \
            or not isinstance(binary_sha, str) or SHA256.fullmatch(binary_sha) is None:
        raise ValueError("5090 profile, queue isolation or Sage binary identity is missing")
    binary = Path(binary_path)
    if binary.is_symlink() or not binary.is_file():
        raise ValueError("Sage binary path is missing or redirected")
    hashes["sage_binary"] = sha256_file(binary)
    if hashes["sage_binary"] != binary_sha:
        raise ValueError("Sage binary bytes differ from process capture")
    return env


def _reviewed_audio_contract(spec: EvidenceFiles, hashes: dict[str, str]) -> AudioContract | None:
    if spec.audio_addendum is None:
        return None
    addendum = _read_json(spec.audio_addendum, hashes, "audio_addendum")
    if hashes["audio_addendum"] != APPROVED_AUDIO_ADDENDUM_SHA256:
        raise ValueError("audio addendum SHA-256 is not pre-approved")
    if not isinstance(addendum, dict) \
            or set(addendum) != {"schema_version", "base_manifest_sha256",
                                 "c1_validation_sha256", "c1_video_sha256",
                                 "c1_video_bytes", "primary_evidence_sha256",
                                 "audio_contract", "scope", "review_id"} \
            or addendum["schema_version"] != 1 \
            or addendum["base_manifest_sha256"] != hashes["manifest"] \
            or addendum["c1_validation_sha256"] != C1_VALIDATION_SHA256 \
            or addendum["c1_video_sha256"] != C1_VIDEO_SHA256 \
            or addendum["c1_video_bytes"] != 9947111 \
            or addendum["primary_evidence_sha256"] != C1_AUDIO_EVIDENCE_SHA256 \
            or addendum["scope"] != "technical_media_format_only_not_visual_or_audio_quality_acceptance" \
            or addendum["review_id"] != "astra-a3-c1-audio-20260926" \
            or addendum["audio_contract"] != {"codec": "aac", "sample_rate": 32000,
                                               "channels": 2}:
        raise ValueError("audio addendum does not bind the reviewed C1 evidence")
    return AudioContract(32000, 2)


def _media(spec: EvidenceFiles, history: dict,
           handoff: dict | None,
           hashes: dict[str, str]) -> dict[str, Any]:
    audio_contract = _reviewed_audio_contract(spec, hashes)
    if spec.output_root is None or spec.video_baseline is None \
            or spec.latent_baseline is None:
        raise FileNotFoundError("source output or pre-submit baselines are missing")
    video_baseline = _read_json(spec.video_baseline, hashes, "video_baseline")
    latent_baseline = _read_json(spec.latent_baseline, hashes, "latent_baseline")
    if handoff is not None:
        claimed = datetime.fromisoformat(handoff["claimed_at_utc"])
        if any(datetime.fromisoformat(item["captured_at_utc"]) > claimed
               for item in (video_baseline, latent_baseline)):
            raise ValueError("output baseline was captured after submission claim")
    graph = history[spec.prompt_id]["prompt"][2]
    video_prefix = graph["264"]["inputs"]["filename_prefix"]
    latent_prefix = graph["400"]["inputs"]["filename_prefix"]
    video, latent = history_output_paths(
        history, spec.prompt_id, spec.output_root, video_prefix, latent_prefix,
        video_baseline, latent_baseline, spec.run_id)
    video_info = inspect_video(video, audio_contract)
    if audio_contract is not None:
        video_info["reviewed_audio_contract"] = {"tier": "derived_verified",
                                                 "addendum_sha256": hashes["audio_addendum"]}
    latent_info = inspect_latent(latent)
    hashes["video"] = sha256_file(video)
    hashes["latent"] = sha256_file(latent)
    if video_info["sha256"] != hashes["video"] \
            or latent_info["sha256"] != hashes["latent"]:
        raise ValueError("media validator hashes differ from source bytes")
    return {"video": video_info, "latent": latent_info,
            "audio_contract_verified": audio_contract is not None}


def _run_check(checks: dict[str, dict[str, Any]], name: str, action) -> Any:
    try:
        value = action()
    except (FileNotFoundError, PermissionError) as exc:
        checks[name] = {"tier": "unknown", "reason": str(exc)}
        return None
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, IndexError,
            json.JSONDecodeError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        checks[name] = {"tier": "INCOMPARABLE", "reason": str(exc)}
        return None
    checks[name] = {"tier": "derived_verified"}
    return value


def _check_source_evidence(spec: EvidenceFiles, manifest: dict, history: dict,
                           history_info: dict, hashes: dict[str, str],
                           checks: dict[str, dict[str, Any]]) -> tuple[dict | None, dict | None, dict | None]:
    handoff = _run_check(checks, "handoff", lambda: _handoff(spec, history_info, hashes))
    sources = _run_check(checks, "assets", lambda: _audit_assets(manifest, spec, hashes))
    env = (_run_check(checks, "environment",
                      lambda: _environment(spec, history_info, sources, hashes, handoff))
           if sources is not None else None)
    if sources is None:
        checks["environment"] = {"tier": "unknown", "reason": "asset audit is incomplete"}
    elif env is not None:
        checks["environment"] = {"tier": "reported_only",
                                 "crosscheck": "raw_file_hash_source_and_handoff_match"}
        if spec.profile == "rtx5090":
            checks["candidate_profile"] = {"tier": "reported_only",
                                            "gpu_name": env["gpu_name"],
                                            "compute_capability": env["compute_capability"]}
    media = _run_check(checks, "media", lambda: _media(spec, history,
                                                       handoff, hashes))
    if media is not None and not media["audio_contract_verified"]:
        checks["media"] = {"tier": "unknown", "reason": "approved audio contract is missing"}
    if env is not None and spec.telemetry is not None:
        telemetry_result = _run_check(checks, "telemetry", lambda: verify_telemetry(
            spec.telemetry, env["gpu_uuid"], env["device_index"],
            history_info["started_at_utc"], history_info["finished_at_utc"],
            run_id=spec.run_id, process_pid=env["process_pid"]))
        if telemetry_result is not None:
            checks["telemetry"]["sensor_tier"] = "reported_only"
            try:
                hashes["telemetry"] = sha256_file(spec.telemetry)
            except OSError as exc:
                checks["telemetry"] = {"tier": "unknown", "reason": str(exc)}
            if "telemetry" in hashes \
                    and hashes["telemetry"] != telemetry_result["raw_sha256"]["value"]:
                checks["telemetry"] = {"tier": "INCOMPARABLE",
                                       "reason": "telemetry bytes changed during validation"}
    else:
        checks["telemetry"] = {"tier": "unknown", "reason": "environment or telemetry is missing"}
    return handoff, env, media


def _check_ws(spec: EvidenceFiles, history: dict, handoff: dict | None,
              hashes: dict[str, str], checks: dict[str, dict[str, Any]]) -> None:
    if spec.trace is None:
        checks["ws"] = {"tier": "unknown", "reason": "no prompt-bound WS trace"}
        checks["observer_handshake"] = {"tier": "unknown", "reason": "no observer trace"}
        return
    try:
        trace = _read_json(spec.trace, hashes, "trace")
    except (OSError, ValueError, TypeError) as exc:
        checks["ws"] = {"tier": "unknown", "reason": str(exc)}
        checks["observer_handshake"] = {"tier": "unknown", "reason": "observer trace unreadable"}
        return
    if not isinstance(trace, dict):
        checks["ws"] = {"tier": "unknown", "reason": "WS trace root is malformed"}
        checks["observer_handshake"] = {"tier": "unknown", "reason": "WS trace root is malformed"}
        return
    if trace.get("run_id") != spec.run_id \
            or trace.get("graph_sha256") != hashes["submitted_graph"] \
            or (handoff and trace.get("client_id") != handoff["client_id"]):
        checks["ws"] = {"tier": "INCOMPARABLE", "reason": "WS trace identity differs"}
        checks["observer_handshake"] = {"tier": "INCOMPARABLE", "reason": "observer identity differs"}
        return
    events = trace.get("events")
    first = events[0] if isinstance(events, list) and events else None
    first_message = first.get("message") if isinstance(first, dict) else None
    first_data = first_message.get("data") if isinstance(first_message, dict) else None
    if handoff and isinstance(first_data, dict) and first_message.get("type") == "status" \
            and (first_data.get("sid") != handoff["client_id"]
                 or first.get("received_at_utc") != handoff["ready_at_utc"]):
        checks["observer_handshake"] = {"tier": "INCOMPARABLE",
                                        "reason": "ready record contradicts WS handshake"}
        checks["ws"] = {"tier": "unknown", "reason": "observer handshake contradicted"}
        return
    if not handoff or not isinstance(first_data, dict) \
            or first_message.get("type") != "status" \
            or first_data.get("sid") != handoff["client_id"] \
            or first.get("received_at_utc") != handoff["ready_at_utc"]:
        checks["observer_handshake"] = {"tier": "unknown",
                                        "reason": "observer handshake is not bound to ready record"}
    else:
        checks["observer_handshake"] = {"tier": "derived_verified"}
    progress = evaluate_progress(trace, history, spec.prompt_id)
    if progress.state == "derived_verified":
        if handoff is None:
            checks["ws"] = {"tier": "unknown", "reason": "observer handoff is missing"}
            return
        messages = history[spec.prompt_id]["status"]["messages"]
        timestamps = {kind: details["timestamp"] for kind, details in messages
                      if kind in {"execution_start", "execution_success"}}
        start = datetime.fromtimestamp(timestamps["execution_start"] / 1000, timezone.utc)
        finish = datetime.fromtimestamp(timestamps["execution_success"] / 1000, timezone.utc)
        first = datetime.fromisoformat(progress.first_received_at_utc)
        last = datetime.fromisoformat(progress.last_received_at_utc)
        if first < start - timedelta(seconds=2) or last > finish + timedelta(seconds=10):
            checks["ws"] = {"tier": "INCOMPARABLE",
                            "reason": "sampler WS events fall outside history interval"}
            return
    checks["ws"] = ({"tier": "derived_verified",
                     "observed_node_interval_s": progress.observed_node_interval_s}
                    if progress.state == "derived_verified" else
                    {"tier": "unknown", "reason": progress.reason})


def evaluate_files(spec: EvidenceFiles) -> dict[str, Any]:
    """Never promote independent reports; always re-read the source files."""
    hashes: dict[str, str] = {}
    checks: dict[str, dict[str, Any]] = {}
    checks["candidate_profile"] = {"tier": "unknown",
                                   "reason": "5090 runtime identity is not verified"}
    graph_data = _run_check(checks, "graph_parent", lambda: _check_graph(spec, hashes))
    if graph_data is None:
        return {"status": decide(checks), "checks": checks, "evidence_sha256": hashes}
    manifest, _, candidate = graph_data
    history = _run_check(checks, "history", lambda: _read_json(spec.history, hashes, "history"))
    history_info = (_run_check(checks, "history", lambda: derive_history(history, spec.prompt_id, candidate))
                    if history is not None else None)
    if history_info is None:
        return {"status": decide(checks), "checks": checks, "evidence_sha256": hashes}
    handoff, env, media = _check_source_evidence(
        spec, manifest, history, history_info, hashes, checks)
    _check_ws(spec, history, handoff, hashes, checks)
    return {"run_id": spec.run_id, "prompt_id": spec.prompt_id,
            "profile": spec.profile,
            "status": decide(checks), "checks": checks,
            "history": history_info, "media": media,
            "environment_tier": "reported_only" if env is not None else "unknown",
            "evidence_sha256": hashes}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run_id", "prompt_id", "profile"):
        parser.add_argument("--" + name.replace("_", "-"), required=True)
    for name in ("manifest", "reference_graph", "submitted_graph", "history", "parent"):
        parser.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    for name in ("output_root", "comfy_root", "runner_root", "ready", "attempt",
                 "prompt_file", "trace", "video_baseline", "latent_baseline",
                 "telemetry", "environment", "audio_addendum"):
        parser.add_argument("--" + name.replace("_", "-"), type=Path)
    args = parser.parse_args()
    result = evaluate_files(EvidenceFiles(**vars(args)))
    print(json.dumps(result, indent=2))
    return 2 if result["status"] == "INCOMPARABLE" else 0


if __name__ == "__main__":
    raise SystemExit(main())
