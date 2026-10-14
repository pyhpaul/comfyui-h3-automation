"""Derive tiered Gate 0 fields from history, graph, parent and optional WS trace."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from h3_cross_gpu_gate0 import sha256_file
from h3_gate0_progress import evaluate_progress


def derive_history(history: dict[str, Any], prompt_id: str,
                   submitted_graph: dict[str, Any]) -> dict[str, Any]:
    if set(history) != {prompt_id}:
        raise ValueError("history is not isolated to target prompt")
    record = history[prompt_id]
    prompt = record.get("prompt")
    if not isinstance(prompt, list) or len(prompt) < 4 or prompt[1] != prompt_id \
            or prompt[2] != submitted_graph:
        raise ValueError("history does not contain submitted graph")
    status = record.get("status")
    if not isinstance(status, dict) or status.get("status_str") != "success" \
            or status.get("completed") is not True:
        raise ValueError("prompt did not complete successfully")
    messages = status.get("messages")
    if not isinstance(messages, list) or any(
            not isinstance(item, list) or len(item) != 2
            or not isinstance(item[1], dict) or item[1].get("prompt_id") != prompt_id
            for item in messages):
        raise ValueError("history messages are malformed or foreign")
    by_kind = {kind: payload for kind, payload in messages}
    required = {"execution_start", "execution_cached", "execution_success"}
    if len(by_kind) != len(messages) or not required.issubset(by_kind):
        raise ValueError("history execution markers are missing or repeated")
    cached = by_kind["execution_cached"].get("nodes")
    if not isinstance(cached, list) or "226" in cached:
        raise ValueError("sampler was cached or cache state is unknown")
    start_ms = by_kind["execution_start"].get("timestamp")
    end_ms = by_kind["execution_success"].get("timestamp")
    if not isinstance(start_ms, int) or not isinstance(end_ms, int) or start_ms >= end_ms:
        raise ValueError("invalid history timestamps")
    return {"prompt_id": prompt_id,
            "client_id": prompt[3].get("client_id") if isinstance(prompt[3], dict) else None,
            "graph": {"tier": "derived_verified", "matches_submitted": True},
            "cache": {"tier": "derived_verified", "sampler_executed": True,
                      "cached_nodes": cached},
            "server_wall_s": {"tier": "derived_verified", "value": (end_ms-start_ms)/1000},
            "started_at_utc": datetime.fromtimestamp(start_ms / 1000, timezone.utc).isoformat(),
            "finished_at_utc": datetime.fromtimestamp(end_ms / 1000, timezone.utc).isoformat()}


def derive_receipt(history: dict[str, Any], prompt_id: str,
                   submitted_graph: dict[str, Any], parent_file: Path | None = None,
                   trace: dict[str, Any] | None = None) -> dict[str, Any]:
    result = derive_history(history, prompt_id, submitted_graph)
    result["parent_sha256"] = ({"tier": "derived_verified", "value": sha256_file(parent_file)}
                               if parent_file is not None else {"tier": "unknown"})
    progress = evaluate_progress(trace, history, prompt_id) if trace is not None else None
    result["sampler_steps"] = ({"tier": "derived_verified", "value": list(progress.steps)}
                               if progress and progress.state == "derived_verified"
                               else {"tier": "unknown", "reason": progress.reason if progress else "no WS trace"})
    result["observed_node_interval_s"] = (
        {"tier": "derived_verified", "value": progress.observed_node_interval_s,
         "clock": "observer_receive_monotonic"}
        if progress and progress.state == "derived_verified" else {"tier": "unknown"})
    result["sampler_wall_s"] = {"tier": "unknown", "reason": "WS receive interval is not execution wall"}
    result["gpu_sensor_values"] = {"tier": "reported_only"}
    outputs = history[prompt_id].get("outputs", {})
    try:
        video_path = outputs["264"]["gifs"][0]["fullpath"]
        latent_path = outputs["405"]["text"][0]
        result["output_history_paths"] = {"tier": "reported_only",
                                          "video": video_path, "latent": latent_path}
    except (KeyError, IndexError, TypeError):
        result["output_history_paths"] = {"tier": "unknown"}
    result["output_media"] = {"tier": "unknown", "reason": "source-side bytes not supplied"}
    result["status"] = "HISTORY_ONLY_NOT_SCREEN"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--submitted-graph", type=Path, required=True)
    parser.add_argument("--prompt-id", required=True)
    parser.add_argument("--parent-file", type=Path)
    parser.add_argument("--trace", type=Path)
    args = parser.parse_args()
    try:
        history = json.loads(args.history.read_text())
        graph = json.loads(args.submitted_graph.read_text())
        trace = json.loads(args.trace.read_text()) if args.trace else None
        print(json.dumps(derive_receipt(history, args.prompt_id, graph,
                                        args.parent_file, trace), indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "INCOMPARABLE", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
