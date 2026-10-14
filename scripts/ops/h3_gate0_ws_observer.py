"""Read-only, single-socket ComfyUI event capture for a separately approved run.

This program never submits, retries, or cancels a prompt. Its ready file is
created only after the server echoes the fresh client ID in a status message.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from h3_gate0_handoff import SHA256, publish_json_exclusive

MAX_OBSERVED_EVENTS = 4096
MAX_OBSERVED_BYTES = 16 * 1024 * 1024


def _ws_url(base_url: str, client_id: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"ws", "wss"} or not parsed.netloc or parsed.path != "/ws":
        raise ValueError("expected an explicit ws:// or wss:// URL ending in /ws")
    if parsed.query or parsed.fragment:
        raise ValueError("WebSocket URL must not contain query or fragment")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path,
                       urlencode({"clientId": client_id}), ""))


def _endpoint(base_url: str) -> str:
    parsed = urlsplit(base_url)
    return urlunsplit(("https" if parsed.scheme == "wss" else "http",
                       parsed.netloc, "", "", ""))


def _event(message: dict[str, Any]) -> dict[str, Any]:
    return {"received_at_utc": datetime.now(timezone.utc).isoformat(),
            "received_monotonic_ns": time.monotonic_ns(), "message": message}


def _target_prompt(path: Path, run_id: str, client_id: str) -> str | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text())
    if value.get("run_id") != run_id or value.get("client_id") != client_id:
        raise ValueError("published prompt ID does not match observer run")
    prompt_id = value.get("prompt_id")
    return prompt_id if isinstance(prompt_id, str) and prompt_id else None


def _target_terminal_index(events: list[dict[str, Any]], prompt_id: str) -> int | None:
    matches = [index for index, event in enumerate(events)
               if event["message"].get("type") == "executing"
               and isinstance(event["message"].get("data"), dict)
               and event["message"]["data"].get("prompt_id") == prompt_id
               and event["message"]["data"].get("node", "missing") is None]
    return matches[0] if len(matches) == 1 else None


async def observe(url: str, ready_file: Path, trace_file: Path,
                  prompt_id_file: Path, timeout_s: float = 3600,
                  *, run_id: str, graph_sha256: str) -> dict[str, Any]:
    """Capture one connection; a disconnect never causes a reconnection."""
    import aiohttp

    raw_file = trace_file.with_suffix(".events.jsonl")
    closed_file = ready_file.with_suffix(".closed.json")
    if timeout_s <= 0 or timeout_s > 7200 or not run_id or not SHA256.fullmatch(graph_sha256) \
            or ready_file.exists() or trace_file.exists() or raw_file.exists() \
            or prompt_id_file.exists() or closed_file.exists():
        raise ValueError("timeout must be within 2 hours and output paths must be unused")
    client_id = str(uuid.uuid4())
    trace: dict[str, Any] = {"run_id": run_id, "graph_sha256": graph_sha256,
                             "client_id": client_id, "events": [],
                             "closed_reason": "not_connected"}
    deadline = time.monotonic() + timeout_s
    terminal_before_id = False
    observed_bytes = 0
    try:
        async with aiohttp.ClientSession() as session:
            connection = await asyncio.wait_for(
                session.ws_connect(_ws_url(url, client_id), heartbeat=None,
                                   max_msg_size=4 * 1024 * 1024),
                timeout=max(0.001, deadline - time.monotonic()))
            async with connection as ws:
                trace["closed_reason"] = "disconnected"
                while True:
                    try:
                        target = _target_prompt(prompt_id_file, run_id, client_id)
                    except (ValueError, TypeError, json.JSONDecodeError):
                        trace["closed_reason"] = "invalid_prompt_id"
                        break
                    terminal_index = (_target_terminal_index(trace["events"], target)
                                      if target else None)
                    if terminal_index is not None:
                        trace["closed_reason"] = "terminal"
                        if terminal_before_id:
                            trace["reconciliation"] = {"method": "late_prompt_id",
                                                       "terminal_event_index": terminal_index}
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        trace["closed_reason"] = "timeout"
                        break
                    try:
                        frame = await asyncio.wait_for(ws.receive(), timeout=min(remaining, 0.25))
                    except asyncio.TimeoutError:
                        continue
                    frame_bytes = (len(frame.data) if frame.type == aiohttp.WSMsgType.BINARY
                                   else len(frame.data.encode("utf-8"))
                                   if frame.type == aiohttp.WSMsgType.TEXT else 0)
                    if len(trace["events"]) >= MAX_OBSERVED_EVENTS \
                            or observed_bytes + frame_bytes > MAX_OBSERVED_BYTES:
                        trace["closed_reason"] = "event_limit"
                        break
                    observed_bytes += frame_bytes
                    if frame.type == aiohttp.WSMsgType.BINARY:
                        message = {"type": "binary_frame", "bytes": len(frame.data),
                                   "sha256": hashlib.sha256(frame.data).hexdigest()}
                    elif frame.type == aiohttp.WSMsgType.TEXT:
                        try:
                            message = json.loads(frame.data)
                        except json.JSONDecodeError:
                            trace["closed_reason"] = "invalid_json"
                            break
                        if not isinstance(message, dict):
                            trace["closed_reason"] = "invalid_message"
                            break
                    else:
                        trace["closed_reason"] = "disconnected"
                        break
                    event = _event(message)
                    trace["events"].append(event)
                    if not target and message.get("type") == "executing" \
                            and isinstance(message.get("data"), dict) \
                            and message["data"].get("node", "missing") is None:
                        terminal_before_id = True
                    with raw_file.open("a") as stream:
                        stream.write(json.dumps(event) + "\n")
                        stream.flush()
                        os.fsync(stream.fileno())
                    if len(trace["events"]) == 1:
                        data = message.get("data")
                        if message.get("type") != "status" or not isinstance(data, dict) \
                                or data.get("sid") != client_id:
                            trace["closed_reason"] = "handshake_mismatch"
                            break
                        publish_json_exclusive(ready_file, {
                            "run_id": run_id, "graph_sha256": graph_sha256,
                            "endpoint": _endpoint(url), "websocket_url": url,
                            "client_id": client_id, "observer_state": "connected",
                            "observer_pid": os.getpid(),
                            "ready_at_utc": trace["events"][0]["received_at_utc"]})
    except asyncio.TimeoutError:
        trace["closed_reason"] = "timeout"
    except (aiohttp.ClientError, OSError) as exc:
        trace["closed_reason"] = f"connection_error:{type(exc).__name__}"
    finally:
        trace_file.write_text(json.dumps(trace, indent=2) + "\n")
        publish_json_exclusive(closed_file, {"run_id": run_id,
                                             "client_id": client_id,
                                             "closed_reason": trace["closed_reason"],
                                             "closed_at_utc": datetime.now(timezone.utc).isoformat()})
    return trace


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="ComfyUI WebSocket URL without query")
    parser.add_argument("--ready-file", type=Path, required=True)
    parser.add_argument("--trace-file", type=Path, required=True)
    parser.add_argument("--prompt-id-file", type=Path, required=True)
    parser.add_argument("--timeout-s", type=float, default=3600)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--graph-sha256", required=True)
    args = parser.parse_args()
    trace = asyncio.run(observe(args.url, args.ready_file, args.trace_file,
                                args.prompt_id_file, args.timeout_s,
                                run_id=args.run_id, graph_sha256=args.graph_sha256))
    print(json.dumps({"closed_reason": trace["closed_reason"],
                      "client_id": trace["client_id"],
                      "events": len(trace["events"])}))
    return 0 if trace["closed_reason"] == "terminal" else 2


if __name__ == "__main__":
    raise SystemExit(main())
