"""At-most-once handoff core with an injected transport.

This module does not create a network client. The Stage B adapter is separate
and must be reviewed and explicitly authorized before a live submission.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit


SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def publish_json_exclusive(path: Path, data: dict[str, Any]) -> None:
    """Publish one complete JSON file without replacing an existing target."""
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(data, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_endpoint(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return (parsed.scheme in {"http", "https"} and bool(parsed.netloc)
            and parsed.hostname is not None and parsed.username is None
            and parsed.password is None and not parsed.path
            and not parsed.query and not parsed.fragment)


@dataclass(frozen=True)
class HandoffSpec:
    run_id: str
    graph_sha256: str
    endpoint: str
    graph_path: Path
    run_dir: Path
    max_ready_age_s: float = 30.0

    @property
    def ready_path(self) -> Path:
        return self.run_dir / "ready.json"

    @property
    def attempt_path(self) -> Path:
        return self.run_dir / "attempt.json"

    @property
    def prompt_id_path(self) -> Path:
        return self.run_dir / "prompt.json"


def _load_ready(spec: HandoffSpec) -> dict[str, Any]:
    ready = json.loads(spec.ready_path.read_text())
    expected = {"run_id": spec.run_id, "graph_sha256": spec.graph_sha256,
                "endpoint": spec.endpoint, "observer_state": "connected"}
    if not valid_endpoint(ready.get("endpoint")) \
            or any(ready.get(key) != value for key, value in expected.items()):
        raise ValueError("observer ready record does not match this run")
    if spec.ready_path.with_suffix(".closed.json").exists():
        raise ValueError("observer has already closed")
    client_id = ready.get("client_id")
    if not isinstance(client_id, str) or str(uuid.UUID(client_id)) != client_id:
        raise ValueError("observer client ID is invalid")
    ready_at = datetime.fromisoformat(ready["ready_at_utc"])
    age = (datetime.now(timezone.utc) - ready_at).total_seconds()
    if ready_at.tzinfo is None or not 0 <= age <= spec.max_ready_age_s:
        raise ValueError("observer readiness is stale")
    pid = ready.get("observer_pid")
    if not isinstance(pid, int) or pid <= 0:
        raise ValueError("observer PID is missing")
    try:
        os.kill(pid, 0)
    except ProcessLookupError as exc:
        raise ValueError("observer process is no longer running") from exc
    return ready


def _claim_attempt(spec: HandoffSpec, client_id: str) -> str:
    attempt_id = str(uuid.uuid4())
    claim = {"attempt_id": attempt_id, "run_id": spec.run_id,
             "graph_sha256": spec.graph_sha256, "client_id": client_id,
             "endpoint": spec.endpoint,
             "claimed_at_utc": _utc_now(), "state": "transport_may_have_started"}
    publish_json_exclusive(spec.attempt_path, claim)
    return attempt_id


def submit_once(spec: HandoffSpec,
                transport: Callable[[str, dict[str, Any]], dict[str, Any]]) -> str:
    """Consume the attempt before calling the supplied transport exactly once."""
    if not spec.run_id or spec.run_dir.name != spec.run_id \
            or not SHA256.fullmatch(spec.graph_sha256) \
            or not valid_endpoint(spec.endpoint) \
            or not 0 < spec.max_ready_age_s <= 30:
        raise ValueError("invalid run namespace, endpoint, graph hash or readiness limit")
    if spec.prompt_id_path.exists():
        raise ValueError("prompt ID already published")
    raw_graph = spec.graph_path.read_bytes()
    if hashlib.sha256(raw_graph).hexdigest() != spec.graph_sha256:
        raise ValueError("submitted graph bytes differ")
    graph = json.loads(raw_graph)
    if not isinstance(graph, dict):
        raise ValueError("submitted graph is not an object")
    ready = _load_ready(spec)
    _claim_attempt(spec, ready["client_id"])
    if spec.ready_path.with_suffix(".closed.json").exists():
        raise ValueError("observer closed before transport")
    response = transport(spec.endpoint, {"prompt": graph, "client_id": ready["client_id"]})
    if not isinstance(response, dict) or not isinstance(response.get("prompt_id"), str) \
            or not response["prompt_id"]:
        raise ValueError("mock transport returned no unambiguous prompt ID")
    publish_json_exclusive(spec.prompt_id_path, {"run_id": spec.run_id,
                                                 "prompt_id": response["prompt_id"],
                                                 "client_id": ready["client_id"],
                                                 "graph_sha256": spec.graph_sha256,
                                                 "endpoint": spec.endpoint,
                                                 "attempt_id": json.loads(spec.attempt_path.read_text())["attempt_id"],
                                                 "published_at_utc": _utc_now()})
    return response["prompt_id"]


def mock_submit_once(spec: HandoffSpec,
                     transport: Callable[[str, dict[str, Any]], dict[str, Any]]) -> str:
    """Compatibility name for offline fixtures; delegates to the same core."""
    return submit_once(spec, transport)
