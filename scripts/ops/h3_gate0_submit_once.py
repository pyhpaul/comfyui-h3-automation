"""Stage B one-shot ComfyUI submit adapter; never upload, retry or poll.

Dry-run is the default. A live POST requires --execute-once and a deadline,
plus separate operator authorization and runtime/source admission.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import socket
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from h3_cross_gpu_gate0 import compare_graphs
from h3_gate0_handoff import HandoffSpec, submit_once, valid_endpoint


FROZEN_MANIFEST_SHA256 = "9a5f0d43b7e93a0fc5a3226c1970f79e88db03550cfc57dbbdcb502c5beb4609"
MAX_RESPONSE_BYTES = 256 * 1024
MAX_HTTP_TIMEOUT_S = 30.0


def _load_checked_graph(manifest_file: Path, reference_file: Path,
                        graph_file: Path, parent_file: Path,
                        output_root: Path, input_root: Path,
                        run_id: str) -> str:
    manifest_raw = manifest_file.read_bytes()
    if hashlib.sha256(manifest_raw).hexdigest() != FROZEN_MANIFEST_SHA256:
        raise ValueError("comparison manifest SHA-256 differs from frozen version")
    manifest = json.loads(manifest_raw)
    reference_raw = reference_file.read_bytes()
    if hashlib.sha256(reference_raw).hexdigest() != manifest["reference_graph_sha256"]:
        raise ValueError("reference graph differs from frozen manifest")
    graph_raw = graph_file.read_bytes()
    graph = json.loads(graph_raw)
    compare_graphs(manifest, json.loads(reference_raw), graph,
                   "rtx5090", parent_file, output_root, input_root, run_id)
    return hashlib.sha256(graph_raw).hexdigest()


def _local_endpoint(endpoint: str) -> tuple[str, int]:
    parsed = urlsplit(endpoint)
    if not valid_endpoint(endpoint) or parsed.scheme != "http" \
            or parsed.hostname not in {"127.0.0.1", "::1"}:
        raise ValueError("live submit endpoint must be local plain HTTP")
    port = parsed.port or 80
    if not 1 <= port <= 65535:
        raise ValueError("live submit endpoint port is invalid")
    return parsed.hostname, port


def _deadline(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("deadline must be UTC")
    return parsed


def _remaining(deadline: float) -> float:
    value = deadline - time.monotonic()
    if value <= 0:
        raise TimeoutError("HTTP submit deadline passed; do not retry")
    return value


def post_prompt_once(endpoint: str, payload: dict[str, Any], timeout_s: float) -> dict[str, Any]:
    """Exactly one HTTP POST; any response ambiguity consumes the outer claim."""
    host, port = _local_endpoint(endpoint)
    if not 0 < timeout_s <= MAX_HTTP_TIMEOUT_S:
        raise ValueError("HTTP timeout is outside the bounded range")
    deadline = time.monotonic() + timeout_s
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    connection = http.client.HTTPConnection(host, port, timeout=_remaining(deadline))
    deadline_hit = threading.Event()
    socket_holder: list[socket.socket | None] = [None]

    def abort_at_deadline() -> None:
        deadline_hit.set()
        active_socket = socket_holder[0] or connection.sock
        if active_socket is not None:
            try:
                active_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    timer = threading.Timer(_remaining(deadline), abort_at_deadline)
    timer.daemon = True
    timer.start()
    try:
        connection.connect()
        connection.auto_open = False
        sock = connection.sock
        if deadline_hit.is_set() or sock is None:
            raise TimeoutError("HTTP submit hard deadline passed; do not retry")
        socket_holder[0] = sock
        sock.settimeout(_remaining(deadline))
        connection.request("POST", "/prompt", body=body,
                           headers={"Content-Type": "application/json",
                                    "Accept": "application/json"})
        sock.settimeout(_remaining(deadline))
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError(f"prompt endpoint returned HTTP {response.status}")
        length_header = response.getheader("Content-Length")
        if length_header is None or not length_header.isdecimal() \
                or not 0 < int(length_header) <= MAX_RESPONSE_BYTES:
            raise ValueError("prompt response has no bounded Content-Length")
        response_body = response.read(int(length_header))
        if deadline_hit.is_set() or time.monotonic() >= deadline:
            raise TimeoutError("HTTP submit hard deadline passed; do not retry")
        if len(response_body) != int(length_header):
            raise ValueError("prompt response body is incomplete")
    except (OSError, http.client.HTTPException) as exc:
        if deadline_hit.is_set():
            raise TimeoutError("HTTP submit hard deadline passed; do not retry") from exc
        raise
    finally:
        timer.cancel()
        connection.close()
    result = json.loads(response_body)
    if not isinstance(result, dict) or result.get("node_errors"):
        raise ValueError("prompt response contains node errors or is malformed")
    prompt_id = result.get("prompt_id")
    try:
        valid_id = isinstance(prompt_id, str) and str(uuid.UUID(prompt_id)) == prompt_id
    except ValueError:
        valid_id = False
    if not valid_id:
        raise ValueError("prompt response has no unambiguous UUID")
    return {"prompt_id": prompt_id}


def execute_once(spec: HandoffSpec, deadline: datetime, timeout_s: float) -> str:
    _local_endpoint(spec.endpoint)
    remaining_window = deadline - datetime.now(timezone.utc) if deadline.tzinfo else None
    if remaining_window is None or not 0 < remaining_window.total_seconds() <= 7200:
        raise ValueError("authorized submit deadline is expired or over two hours away")
    if not 0 < timeout_s <= MAX_HTTP_TIMEOUT_S:
        raise ValueError("HTTP timeout is outside the bounded range")

    def transport(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            raise TimeoutError("deadline passed after attempt claim; do not retry")
        return post_prompt_once(endpoint, payload, min(timeout_s, remaining))

    return submit_once(spec, transport)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--reference-graph", type=Path, required=True)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--deadline-utc")
    parser.add_argument("--http-timeout-s", type=float, default=15.0)
    parser.add_argument("--execute-once", action="store_true")
    args = parser.parse_args()
    spec: HandoffSpec | None = None
    try:
        _local_endpoint(args.endpoint)
        if args.run_dir.name != args.run_id:
            raise ValueError("run directory must be named for the run ID")
        if args.output_root.resolve(strict=True).name != "output" \
                or args.input_root.resolve(strict=True) != args.output_root.resolve(strict=True).parent / "input":
            raise ValueError("input root must be the selected ComfyUI root's default input directory")
        graph_sha = _load_checked_graph(args.manifest, args.reference_graph,
                                        args.graph, args.parent, args.output_root,
                                        args.input_root, args.run_id)
        spec = HandoffSpec(args.run_id, graph_sha, args.endpoint, args.graph, args.run_dir)
        if not args.execute_once:
            result = {"status": "DRY_RUN_NO_POST", "run_id": args.run_id,
                      "graph_sha256": graph_sha, "run_dir": str(args.run_dir)}
        else:
            if args.deadline_utc is None:
                raise ValueError("--deadline-utc is required with --execute-once")
            prompt_id = execute_once(spec, _deadline(args.deadline_utc), args.http_timeout_s)
            result = {"status": "SUBMITTED_ONCE", "run_id": args.run_id,
                      "graph_sha256": graph_sha, "prompt_id": prompt_id,
                      "attempt_path": str(spec.attempt_path)}
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, TypeError, KeyError, http.client.HTTPException,
            TimeoutError, json.JSONDecodeError) as exc:
        consumed = spec is not None and spec.attempt_path.exists()
        print(json.dumps({"status": ("ATTEMPT_CONSUMED_RECONCILE" if consumed
                                     else "PRE_SUBMIT_STOP"), "reason": str(exc),
                          "attempt_path": str(spec.attempt_path) if spec else None}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
