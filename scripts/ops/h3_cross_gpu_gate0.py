"""Read-only H3 cross-GPU input, graph, and execution-receipt gates."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from h3_a100_ab_contract import graphs_match_except_candidate, parse_step_timing


class Incomparable(ValueError):
    """The evidence cannot support a matched-input timing screen."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise Incomparable(reason)


def _digest(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _positive(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _nonnegative(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def _timestamp(value: Any) -> datetime:
    _require(isinstance(value, str), "timestamp is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Incomparable("invalid timestamp") from exc
    _require(parsed.tzinfo is not None, "timestamp has no timezone")
    return parsed


def _asset_key(path: str) -> str:
    if path.startswith("/content/h3-rental/ComfyUI/"):
        return path.removeprefix("/content/h3-rental/")
    if path.startswith("/content/h3-runner/"):
        return "runner/" + path.removeprefix("/content/h3-runner/")
    raise Incomparable(f"unexpected preflight asset path: {path}")


def audit_reference(manifest: dict[str, Any], preflight: dict[str, Any],
                    preflight_file: Path, graph_file: Path, parent_file: Path,
                    wheel_file: Path) -> None:
    """Validate the static lock against archived bytes, not the working tree."""
    _require(manifest.get("schema_version") == 1, "unsupported manifest schema")
    _require(sha256_file(preflight_file) == manifest["reference_preflight_sha256"],
             "archived preflight hash changed")
    _require(sha256_file(graph_file) == manifest["reference_graph_sha256"],
             "archived graph hash changed")
    _require(parent_file.stat().st_size == manifest["parent"]["bytes"]
             and sha256_file(parent_file) == manifest["parent"]["sha256"],
             "A100 parent bytes changed")
    _require(sha256_file(wheel_file) == manifest["reference_runtime"]["sage_wheel_sha256"],
             "A100 Sage wheel bytes changed")
    assets = manifest["assets"]
    _require(len(assets) == 13 and [item["path"] for item in assets]
             == sorted(item["path"] for item in assets),
             "manifest assets must be the 13 sorted frozen entries")
    expected = {item["path"]: (item["bytes"], item["sha256"]) for item in assets}
    observed = {_asset_key(item["path"]): (item["bytes"], item["sha256"])
                for item in preflight["assets"]}
    _require(observed == expected and all(item.get("match") is True
                                          for item in preflight["assets"]),
             "preflight assets differ from the frozen manifest")
    graph = json.loads(graph_file.read_text())
    contract = manifest["graph_contract"]
    _require(graph["256"]["inputs"]["noise_seed"] == contract["seed"]
             and graph["255"]["inputs"]["sampler_name"] == contract["sampler"]
             and graph["261"]["inputs"]["scheduler"] == contract["scheduler"]
             and graph["261"]["inputs"]["steps"] == contract["scheduler_steps"]
             and graph["289"]["inputs"]["step"] == contract["split_step"]
             and graph["264"]["inputs"]["frame_rate"] == contract["video_fps"]
             and graph["401"]["inputs"]["latent_path"] == manifest["parent"]["graph_path"],
             "reference graph settings differ from manifest")


def _sage_profile(graph: dict[str, Any]) -> None:
    patch = graph.get("58")
    lora = graph.get("128")
    _require(isinstance(patch, dict) and isinstance(lora, dict),
             "expected Sage node 58 and exact model edge; bypass is not comparable")
    _require(patch.get("class_type")
             == "MiniMaxH3MemoryEfficientSageAttentionPatch"
             and patch.get("inputs") == {"model": ["192", 0]}
             and isinstance(lora.get("inputs"), dict)
             and lora["inputs"].get("model") == ["58", 0],
             "expected Sage node 58 and exact model edge; bypass is not comparable")


def _staging_path(path: str, parent_sha256: str, run_id: str) -> bool:
    return path == f"h3_gate1/{run_id}/parent-{parent_sha256[:16]}.safetensors"


def _normalize_reference_paths(manifest: dict[str, Any], reference: dict[str, Any],
                               candidate: dict[str, Any], run_id: str,
                               input_root: Path | None) -> None:
    assets = {Path(item["path"]).name: item for item in manifest.get("assets", [])
              if item["kind"] == "reference"}
    if not assets:
        return
    reference_images = {
        node_id: node["inputs"]["image"] for node_id, node in reference.items()
        if node.get("class_type") == "LoadImage"
        and isinstance(node.get("inputs"), dict)
        and node["inputs"].get("image") in assets
    }
    _require(len(reference_images) == len(assets)
             and set(reference_images.values()) == set(assets),
             "frozen reference images are not uniquely bound to LoadImage nodes")
    _require(input_root is not None, "5090 input root is required for reference checks")
    root = input_root.resolve(strict=True)
    for node_id, original in reference_images.items():
        node = candidate.get(node_id)
        _require(isinstance(node, dict) and isinstance(node.get("inputs"), dict),
                 "candidate reference node is missing")
        actual = node["inputs"].get("image")
        alias = f"h3_gate1/{run_id}/refs/{original}"
        _require(actual in {original, alias},
                 "reference image path differs outside the hash-bound staging alias")
        image = root / actual
        cursor = root
        for component in Path(actual).parts:
            cursor = cursor / component
            _require(not cursor.is_symlink(), "staged reference path contains a symlink")
        resolved = image.resolve(strict=True)
        _require(resolved.is_relative_to(root), "staged reference image escapes input root")
        expected = assets[original]
        _require(resolved.stat().st_size == expected["bytes"]
                 and sha256_file(resolved) == expected["sha256"],
                 f"reference image bytes differ: {original}")
        candidate[node_id]["inputs"]["image"] = original


def compare_graphs(manifest: dict[str, Any], reference: dict[str, Any],
                   candidate: dict[str, Any], profile: str,
                   parent_file: Path, output_root: Path | None = None,
                   input_root: Path | None = None,
                   expected_run_id: str | None = None) -> None:
    _require(profile in {"a100_sage_sm80", "rtx5090"}, "unsupported comparison profile")
    _require(isinstance(reference, dict) and isinstance(candidate, dict),
             "graph root must be an object")
    _sage_profile(reference)
    _sage_profile(candidate)
    parent = manifest["parent"]
    loader = candidate.get("401")
    _require(isinstance(loader, dict) and isinstance(loader.get("inputs"), dict),
             "candidate parent node is missing")
    actual_path = loader["inputs"].get("latent_path")
    _require(isinstance(actual_path, str), "candidate parent path is missing")
    if profile == "rtx5090":
        _require(isinstance(expected_run_id, str)
                 and re.fullmatch(r"[A-Za-z0-9_-]+", expected_run_id) is not None,
                 "5090 run ID is missing or invalid")
        _require(_staging_path(actual_path, parent["sha256"], expected_run_id),
                 "5090 parent must use a unique hash-bound staging path")
        _require(output_root is not None, "5090 output root is required")
        root = output_root.resolve(strict=True)
        actual_file = (root / actual_path).resolve(strict=True)
        _require(actual_file.is_relative_to(root) and actual_file == parent_file.resolve(strict=True),
                 "parent file is not the graph's staged file")
    else:
        _require(actual_path == parent["graph_path"], "A100 parent path changed")
    _require(parent_file.stat().st_size == parent["bytes"]
             and sha256_file(parent_file) == parent["sha256"],
             "candidate parent bytes differ from frozen A100 parent")
    normalized_candidate = copy.deepcopy(candidate)
    normalized_candidate["401"]["inputs"]["latent_path"] = parent["graph_path"]
    if profile == "rtx5090":
        _normalize_reference_paths(manifest, reference, normalized_candidate,
                                   expected_run_id, input_root)
    try:
        same = graphs_match_except_candidate(reference, normalized_candidate)
    except (KeyError, ValueError) as exc:
        raise Incomparable(f"invalid H3 graph: {exc}") from exc
    _require(same, "submitted graph differs outside the reviewed allowlist")


def validate_history(receipt: dict[str, Any], history: dict[str, Any],
                     candidate: dict[str, Any]) -> None:
    execution = receipt["execution"]
    prompt_id = execution["prompt_id"]
    _require(set(history) == {prompt_id}, "history is not isolated to the target prompt")
    record = history[prompt_id]
    submitted = record.get("prompt", [])
    status = record.get("status", {})
    _require(len(submitted) >= 3 and submitted[1] == prompt_id
             and submitted[2] == candidate,
             "history does not contain the submitted candidate graph")
    _require(status.get("status_str") == "success" and status.get("completed") is True,
             "history did not complete successfully")
    messages = status.get("messages", [])
    _require(all(isinstance(item, list) and len(item) == 2
                 and isinstance(item[1], dict)
                 and item[1].get("prompt_id") == prompt_id for item in messages),
             "history contains a foreign prompt message")
    by_type = {kind: payload for kind, payload in messages}
    _require(len(by_type) == len(messages)
             and {"execution_start", "execution_cached", "execution_success"}.issubset(by_type),
             "history is missing unique execution markers")
    cached = by_type["execution_cached"].get("nodes")
    _require(isinstance(cached, list) and "226" not in cached,
             "sampler node was cached")
    start_ms = by_type["execution_start"].get("timestamp")
    end_ms = by_type["execution_success"].get("timestamp")
    _require(isinstance(start_ms, int) and isinstance(end_ms, int) and start_ms < end_ms,
             "history timestamps are invalid")
    start = _timestamp(execution["started_at_utc"])
    end = _timestamp(execution["finished_at_utc"])
    _require(abs(start.timestamp() * 1000 - start_ms) <= 1
             and abs(end.timestamp() * 1000 - end_ms) <= 1
             and abs(execution["server_wall_s"] - (end_ms - start_ms) / 1000) <= 0.01,
             "server timing is not bound to history")


def validate_sampler_log(receipt: dict[str, Any], log_file: Path) -> None:
    log = log_file.read_text(errors="replace")
    _require(sha256_file(log_file) == receipt["execution"].get("sampler_log_sha256"),
             "sampler log hash differs from receipt")
    _require(len(re.findall(r"\bgot prompt\b", log)) == 1
             and len(re.findall(r"Prompt executed in", log)) == 1,
             "sampler log is not a single-prompt slice")
    try:
        parsed = parse_step_timing(log)
    except ValueError as exc:
        raise Incomparable(f"sampler log lacks 12 steps: {exc}") from exc
    steps = receipt["execution"]["steps"]
    _require(tuple(step["elapsed_s"] for step in steps) == parsed.elapsed_seconds,
             "sampler receipt steps differ from isolated log")


def validate_receipt(manifest: dict[str, Any], manifest_sha256: str,
                     candidate_graph_sha256: str, receipt: dict[str, Any],
                     profile: str, parent_graph_path: str) -> None:
    """Reject incomplete or cross-prompt evidence before timing comparison."""
    _require(receipt.get("schema_version") == 1, "unsupported receipt schema")
    _require(receipt.get("manifest_sha256") == manifest_sha256,
             "receipt is not bound to this manifest")
    _require(receipt.get("graph_sha256") == candidate_graph_sha256,
             "receipt is not bound to this submitted graph")
    _require(receipt.get("profile") == profile, "receipt profile differs")
    _require(receipt.get("parent_graph_path") == parent_graph_path
             and receipt.get("parent_sha256") == manifest["parent"]["sha256"],
             "receipt parent differs")
    expected = {item["path"]: item for item in manifest["assets"]}
    observed = receipt.get("assets")
    _require(isinstance(observed, dict) and set(observed) == set(expected),
             "receipt asset inventory is incomplete")
    for path, asset in expected.items():
        item = observed[path]
        _require(isinstance(item, dict) and _digest(item.get("sha256"))
                 and _positive(item.get("bytes")),
                 f"asset size/hash missing: {path}")
        if asset["kind"] != "source":
            _require(item["bytes"] == asset["bytes"]
                     and item["sha256"] == asset["sha256"],
                     f"model, prompt or reference changed: {path}")
        elif item["sha256"] != asset["sha256"] or item["bytes"] != asset["bytes"]:
            approvals = manifest.get("approved_source_deltas", {}).get(path, [])
            _require(any(isinstance(approval, dict)
                         and approval.get("sha256") == item["sha256"]
                         and approval.get("bytes") == item["bytes"]
                         and isinstance(approval.get("review_id"), str)
                         and bool(approval["review_id"].strip())
                         for approval in approvals),
                     f"source delta is not file-specifically approved: {path}")
    environment = receipt.get("environment")
    _require(isinstance(environment, dict), "environment receipt is missing")
    for key in ("gpu", "driver", "sm_clock", "python", "torch", "cuda",
                "sage_binary_sha256", "comfyui", "startup_flags", "process_started_at_utc",
                "process_pid"):
        _require(environment.get(key) not in (None, "", "unknown"),
                 f"environment field is missing: {key}")
    _require(_digest(environment["sage_binary_sha256"]), "invalid Sage binary SHA-256")
    _require(isinstance(environment["process_pid"], int)
             and environment["process_pid"] > 0, "invalid server process PID")
    _timestamp(environment["process_started_at_utc"])
    execution = receipt.get("execution")
    _require(isinstance(execution, dict), "execution receipt is missing")
    prompt_id = execution.get("prompt_id")
    _require(isinstance(prompt_id, str) and bool(prompt_id), "prompt ID is missing")
    start = _timestamp(execution.get("started_at_utc"))
    end = _timestamp(execution.get("finished_at_utc"))
    _require(start < end and execution.get("history_status") == "success"
             and execution.get("cache_status") == "executed"
             and execution.get("interleaved_prompts") is False
             and execution.get("sampler_node_id") == "226",
             "prompt interval, cache or sampler identity is not proven")
    capture = execution.get("log_capture")
    _require(isinstance(capture, dict)
             and capture.get("method") == "append_only_byte_range"
             and capture.get("process_pid") == environment["process_pid"]
             and _nonnegative(capture.get("byte_start"))
             and _positive(capture.get("byte_end"))
             and capture["byte_start"] < capture["byte_end"]
             and _timestamp(capture.get("started_at_utc")) <= start
             and end <= _timestamp(capture.get("finished_at_utc"))
             and _digest(execution.get("sampler_log_sha256")),
             "prompt-bound append-only log capture is missing")
    for key in ("correlation_source", "server_timing_source", "sampler_timing_source"):
        _require(isinstance(execution.get(key), str)
                 and execution[key] not in ("", "unknown", "shared_unattributed"),
                 f"timing correlation is missing: {key}")
    server = execution.get("server_wall_s")
    sampler = execution.get("sampler_wall_s")
    _require(_positive(server) and _positive(sampler) and sampler <= server,
             "server/sampler timing is invalid")
    steps = execution.get("steps")
    _require(isinstance(steps, list) and len(steps) == 12,
             "expected exactly 12 prompt-bound sampler steps")
    timed_steps = all(isinstance(step, dict) and "at_utc" in step for step in steps)
    _require(timed_steps or all(isinstance(step, dict) and "at_utc" not in step
                                for step in steps),
             "partial sampler step timestamps are not comparable")
    prior_at = start
    prior_elapsed = 0.0
    for index, step in enumerate(steps, start=1):
        _require(isinstance(step, dict) and step.get("step") == index
                 and step.get("prompt_id") == prompt_id
                 and step.get("sampler_node_id") == "226",
                 "sampler steps are mixed, missing or out of order")
        elapsed = step.get("elapsed_s")
        _require(_positive(elapsed) and prior_elapsed < elapsed <= sampler + 5,
                 "sampler step is outside the target prompt interval")
        if timed_steps:
            at = _timestamp(step["at_utc"])
            _require(prior_at < at <= end, "sampler step is outside the target prompt interval")
            prior_at = at
        prior_elapsed = elapsed
    telemetry = receipt.get("gpu_telemetry")
    _require(isinstance(telemetry, list) and len(telemetry) >= 2,
             "5-second GPU telemetry is missing")
    prior_at = None
    for sample in telemetry:
        _require(isinstance(sample, dict) and _nonnegative(sample.get("utilization_pct"))
                 and _nonnegative(sample.get("vram_mib")), "invalid GPU sample")
        at = _timestamp(sample.get("at_utc"))
        if prior_at is not None:
            _require(0 < (at - prior_at).total_seconds() <= 7.5,
                     "GPU telemetry gap exceeds 7.5 s")
        prior_at = at
    _require(abs((_timestamp(telemetry[0]["at_utc"]) - start).total_seconds()) <= 10
             and abs((end - _timestamp(telemetry[-1]["at_utc"])).total_seconds()) <= 10,
             "GPU telemetry does not cover the prompt")
    costs = receipt.get("operations_wall_s")
    _require(isinstance(costs, dict) and all(_nonnegative(costs.get(key))
             for key in ("setup", "restore", "transfer", "backup")),
             "operation timing is incomplete")
    media = receipt.get("media")
    _require(isinstance(media, dict) and media.get("latent_finite") is True
             and _positive(media.get("video_frames"))
             and _positive(media.get("audio_frames"))
             and _positive(media.get("video_duration_s"))
             and _positive(media.get("audio_duration_s")),
             "MP4/latent validity is incomplete")
    for key in ("decoded_video_sha256", "decoded_audio_sha256", "latent_sha256",
                "video_timeline_sha256", "audio_timeline_sha256"):
        _require(_digest(media.get(key)), f"media digest is missing: {key}")
    for key in ("video_time_base", "audio_time_base"):
        _require(isinstance(media.get(key), str) and re.fullmatch(r"\d+/\d+", media[key]),
                 f"media time base is missing: {key}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--reference-graph", type=Path, required=True)
    parser.add_argument("--candidate-graph", type=Path)
    parser.add_argument("--parent-file", type=Path, required=True)
    parser.add_argument("--profile", choices=("a100_sage_sm80", "rtx5090"))
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--history", type=Path)
    parser.add_argument("--sampler-log", type=Path)
    parser.add_argument("--reference-preflight", type=Path)
    parser.add_argument("--sage-wheel", type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text())
        reference = json.loads(args.reference_graph.read_text())
        if args.reference_preflight is not None:
            _require(args.sage_wheel is not None, "--sage-wheel required for reference audit")
            preflight = json.loads(args.reference_preflight.read_text())
            audit_reference(manifest, preflight, args.reference_preflight,
                            args.reference_graph, args.parent_file, args.sage_wheel)
        _require(args.candidate_graph is not None or args.reference_preflight is not None,
                 "select a reference audit or candidate graph check")
        if args.candidate_graph is None:
            status = "REFERENCE_AUDIT_OK"
        else:
            _require(args.profile is not None, "--profile required for candidate check")
            _require(sha256_file(args.reference_graph) == manifest["reference_graph_sha256"],
                     "reference graph hash changed")
            candidate = json.loads(args.candidate_graph.read_text())
            compare_graphs(manifest, reference, candidate, args.profile,
                           args.parent_file, args.output_root, args.input_root,
                           args.run_id)
            if args.receipt is not None:
                _require(args.history is not None and args.sampler_log is not None,
                         "--history and --sampler-log required with receipt")
                receipt = json.loads(args.receipt.read_text())
                validate_receipt(manifest, sha256_file(args.manifest),
                                 sha256_file(args.candidate_graph), receipt,
                                 args.profile, candidate["401"]["inputs"]["latent_path"])
                validate_history(receipt, json.loads(args.history.read_text()), candidate)
                validate_sampler_log(receipt, args.sampler_log)
                status = "STRUCTURAL_ONLY"
            else:
                status = "GRAPH_AND_PARENT_ONLY"
        print(json.dumps({"status": status, "manifest_sha256": sha256_file(args.manifest)}))
        return 0
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "INCOMPARABLE", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
