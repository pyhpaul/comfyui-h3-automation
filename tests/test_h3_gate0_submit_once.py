"""Loopback-only Stage B transport tests; no external ComfyUI or GPU."""

import hashlib
import json
import os
import sys
import threading
import time
import copy
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
from h3_gate0_handoff import HandoffSpec, publish_json_exclusive
import h3_gate0_submit_once as stage_b
import h3_gate0_evaluate as gate
from h3_gate0_submit_once import execute_once, post_prompt_once


PROMPT_ID = "33333333-3333-4333-8333-333333333333"
CLIENT_ID = "11111111-1111-4111-8111-111111111111"


def test_frozen_manifest_hash_matches_evaluator():
    assert stage_b.FROZEN_MANIFEST_SHA256 == gate.FROZEN_MANIFEST_SHA256


@contextmanager
def local_prompt_server(mode="success"):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, payload))
            if mode == "timeout":
                time.sleep(0.3)
            if mode == "slow_header":
                for _ in range(50):
                    try:
                        self.wfile.write(b" ")
                        self.wfile.flush()
                    except OSError:
                        return
                    time.sleep(0.02)
                return
            if mode == "near_deadline_header":
                time.sleep(0.06)
            status = 307 if mode == "redirect" else (500 if mode == "error" else 200)
            body = (b"not-json" if mode == "malformed" else
                    json.dumps({"prompt_id": PROMPT_ID}).encode())
            self.send_response(status)
            if mode == "redirect":
                self.send_header("Location", "/prompt")
            if mode == "chunked":
                self.send_header("Transfer-Encoding", "chunked")
            elif mode != "missing_length":
                self.send_header("Content-Length", str(len(body) + (1 if mode == "short_body" else 0)))
            self.end_headers()
            try:
                if mode in {"slow_body", "near_deadline_header"}:
                    for byte in body:
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                        time.sleep(0.02)
                else:
                    self.wfile.write(body)
            except OSError:
                pass

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _spec(tmp_path, endpoint):
    graph = tmp_path / "graph.json"
    graph.write_text('{"226":{"class_type":"Sampler"}}')
    graph_sha = hashlib.sha256(graph.read_bytes()).hexdigest()
    run_dir = tmp_path / "run-once"
    run_dir.mkdir()
    spec = HandoffSpec("run-once", graph_sha, endpoint, graph, run_dir)
    publish_json_exclusive(spec.ready_path, {
        "run_id": spec.run_id, "graph_sha256": graph_sha,
        "endpoint": endpoint, "observer_state": "connected",
        "client_id": CLIENT_ID, "observer_pid": os.getpid(),
        "ready_at_utc": datetime.now(timezone.utc).isoformat()})
    return spec


def test_live_transport_one_post_and_same_client_id(tmp_path):
    with local_prompt_server() as (endpoint, calls):
        spec = _spec(tmp_path, endpoint)
        deadline = datetime.now(timezone.utc) + timedelta(seconds=5)
        assert execute_once(spec, deadline, 2) == PROMPT_ID
        assert calls == [("/prompt", {"prompt": {"226": {"class_type": "Sampler"}},
                                      "client_id": CLIENT_ID})]
        assert json.loads(spec.prompt_id_path.read_text())["prompt_id"] == PROMPT_ID
        with pytest.raises(ValueError, match="already published"):
            execute_once(spec, deadline, 2)
        assert len(calls) == 1


def test_response_timeout_consumes_claim_without_retry(tmp_path):
    with local_prompt_server("timeout") as (endpoint, calls):
        spec = _spec(tmp_path, endpoint)
        deadline = datetime.now(timezone.utc) + timedelta(seconds=5)
        with pytest.raises(TimeoutError):
            execute_once(spec, deadline, 0.05)
        assert spec.attempt_path.exists()
        assert not spec.prompt_id_path.exists()
        with pytest.raises(FileExistsError):
            execute_once(spec, deadline, 1)
        assert len(calls) == 1


@pytest.mark.parametrize("mode", ["slow_header", "slow_body", "near_deadline_header"])
def test_hard_deadline_cuts_off_drip_response(tmp_path, mode):
    with local_prompt_server(mode) as (endpoint, calls):
        spec = _spec(tmp_path, endpoint)
        started = time.monotonic()
        with pytest.raises(TimeoutError, match="deadline"):
            execute_once(spec, datetime.now(timezone.utc) + timedelta(seconds=5), 0.12)
        assert time.monotonic() - started < 0.6
        assert spec.attempt_path.exists()
        assert not spec.prompt_id_path.exists()
        assert len(calls) == 1


@pytest.mark.parametrize("abort_at", ["connect", "before_request"])
def test_deadline_never_auto_reconnects_or_posts(monkeypatch, abort_at):
    state = {"connects": 0, "posts": 0}

    class FakeTimer:
        current = None

        def __init__(self, interval, callback):
            self.callback = callback
            FakeTimer.current = self

        def start(self):
            pass

        def cancel(self):
            pass

    class FakeSocket:
        def __init__(self, connection):
            self.connection = connection

        def settimeout(self, value):
            if abort_at == "before_request":
                FakeTimer.current.callback()

        def shutdown(self, how):
            self.connection.sock = None

    class FakeConnection:
        def __init__(self, host, port, timeout):
            self.sock = None
            self.auto_open = True

        def connect(self):
            state["connects"] += 1
            self.sock = FakeSocket(self)
            if abort_at == "connect":
                FakeTimer.current.callback()

        def request(self, method, path, body, headers):
            if self.sock is None:
                if not self.auto_open:
                    raise OSError("connection was closed before request")
                self.connect()
            state["posts"] += 1

        def close(self):
            self.sock = None

    monkeypatch.setattr(stage_b.http.client, "HTTPConnection", FakeConnection)
    monkeypatch.setattr(stage_b.threading, "Timer", FakeTimer)
    with pytest.raises(TimeoutError, match="deadline"):
        post_prompt_once("http://127.0.0.1:8188", {"prompt": {}}, 1)
    assert state == {"connects": 1, "posts": 0}


@pytest.mark.parametrize("mode", ["missing_length", "chunked", "error", "short_body"])
def test_ambiguous_response_consumes_claim_without_retry(tmp_path, mode):
    with local_prompt_server(mode) as (endpoint, calls):
        spec = _spec(tmp_path, endpoint)
        with pytest.raises((ValueError, OSError)):
            execute_once(spec, datetime.now(timezone.utc) + timedelta(seconds=5), 1)
        assert spec.attempt_path.exists()
        assert not spec.prompt_id_path.exists()
        assert len(calls) == 1


def test_graph_change_after_preflight_stops_before_post(tmp_path):
    with local_prompt_server() as (endpoint, calls):
        spec = _spec(tmp_path, endpoint)
        spec.graph_path.write_text('{"changed":true}')
        with pytest.raises(ValueError, match="submitted graph bytes differ"):
            execute_once(spec, datetime.now(timezone.utc) + timedelta(seconds=5), 1)
        assert not spec.attempt_path.exists()
        assert calls == []


@pytest.mark.parametrize("mode", ["redirect", "malformed"])
def test_redirect_or_malformed_response_never_retries(tmp_path, mode):
    with local_prompt_server(mode) as (endpoint, calls):
        spec = _spec(tmp_path, endpoint)
        with pytest.raises(ValueError):
            execute_once(spec, datetime.now(timezone.utc) + timedelta(seconds=5), 2)
        assert spec.attempt_path.exists()
        assert not spec.prompt_id_path.exists()
        assert len(calls) == 1


def test_nonlocal_endpoint_and_expired_deadline_stop_before_claim(tmp_path):
    with pytest.raises(ValueError, match="local plain HTTP"):
        post_prompt_once("http://fixture.invalid", {"prompt": {}}, 1)
    with pytest.raises(ValueError, match="local plain HTTP"):
        post_prompt_once("http://localhost:8188", {"prompt": {}}, 1)
    with local_prompt_server() as (endpoint, calls):
        spec = _spec(tmp_path, endpoint)
        with pytest.raises(ValueError, match="deadline"):
            execute_once(spec, datetime.now(timezone.utc) - timedelta(seconds=1), 1)
        assert not spec.attempt_path.exists()
        assert calls == []


def test_non_utc_cli_deadline_is_rejected():
    with pytest.raises(ValueError, match="must be UTC"):
        stage_b._deadline("2026-09-26T12:00:00-07:00")


def test_concurrent_live_invocations_post_at_most_once(tmp_path):
    with local_prompt_server() as (endpoint, calls):
        spec = _spec(tmp_path, endpoint)
        deadline = datetime.now(timezone.utc) + timedelta(seconds=5)
        barrier = threading.Barrier(2)

        def invoke():
            barrier.wait()
            try:
                return execute_once(spec, deadline, 2)
            except (FileExistsError, ValueError):
                return "rejected"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: invoke(), range(2)))
        assert sorted(results) == [PROMPT_ID, "rejected"]
        assert len(calls) == 1


def test_cli_dry_run_then_explicit_once_with_same_checked_graph(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(stage_b, "post_prompt_once", lambda *args: pytest.fail("dry-run called transport"))
    output_root = tmp_path / "output"
    input_root = tmp_path / "input"
    input_root.mkdir()
    staged = output_root / "h3_gate1/run-once"
    staged.mkdir(parents=True)
    parent = staged / ("parent-" + hashlib.sha256(b"parent").hexdigest()[:16]
                       + ".safetensors")
    parent.write_bytes(b"parent")
    reference = {
        "58": {"class_type": "MiniMaxH3MemoryEfficientSageAttentionPatch",
               "inputs": {"model": ["192", 0]}},
        "128": {"inputs": {"model": ["58", 0]}},
        "192": {"inputs": {}},
        "264": {"inputs": {"filename_prefix": "gate/video"}},
        "400": {"inputs": {"filename_prefix": "gate/latent"}},
        "401": {"inputs": {"latent_path": "h3_context/parent.safetensors"}}}
    candidate = copy.deepcopy(reference)
    candidate["401"]["inputs"]["latent_path"] = str(parent.relative_to(output_root))
    reference_path = tmp_path / "reference.json"
    graph_path = tmp_path / "graph.json"
    reference_path.write_text(json.dumps(reference))
    graph_path.write_text(json.dumps(candidate))
    manifest = {"reference_graph_sha256": hashlib.sha256(reference_path.read_bytes()).hexdigest(),
                "parent": {"graph_path": "h3_context/parent.safetensors",
                           "sha256": hashlib.sha256(parent.read_bytes()).hexdigest(),
                           "bytes": parent.stat().st_size}}
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setattr(stage_b, "FROZEN_MANIFEST_SHA256",
                        hashlib.sha256(manifest_path.read_bytes()).hexdigest())
    run_dir = tmp_path / "run-once"
    monkeypatch.setattr(sys, "argv", ["h3_gate0_submit_once.py", "--run-id", "run-once",
                                  "--run-dir", str(run_dir), "--endpoint", "http://127.0.0.1:9",
                                  "--manifest", str(manifest_path),
                                  "--reference-graph", str(reference_path),
                                  "--graph", str(graph_path), "--parent", str(parent),
                                  "--output-root", str(output_root),
                                  "--input-root", str(input_root)])
    assert stage_b.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "DRY_RUN_NO_POST"
    assert result["graph_sha256"] == hashlib.sha256(graph_path.read_bytes()).hexdigest()
    assert not (run_dir / "attempt.json").exists()

    run_dir.mkdir()
    spec = HandoffSpec("run-once", result["graph_sha256"], "http://127.0.0.1:9",
                       graph_path, run_dir)
    publish_json_exclusive(spec.ready_path, {
        "run_id": spec.run_id, "graph_sha256": spec.graph_sha256,
        "endpoint": spec.endpoint, "observer_state": "connected",
        "client_id": CLIENT_ID, "observer_pid": os.getpid(),
        "ready_at_utc": datetime.now(timezone.utc).isoformat()})
    calls = []

    def fake_post(endpoint, payload, timeout_s):
        calls.append((endpoint, payload, timeout_s))
        return {"prompt_id": PROMPT_ID}

    monkeypatch.setattr(stage_b, "post_prompt_once", fake_post)
    monkeypatch.setattr(sys, "argv", [*sys.argv, "--execute-once", "--deadline-utc",
                                  (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()])
    assert stage_b.main() == 0
    submitted = json.loads(capsys.readouterr().out)
    assert submitted["status"] == "SUBMITTED_ONCE"
    assert submitted["prompt_id"] == PROMPT_ID
    assert len(calls) == 1
    assert calls[0][0] == spec.endpoint
    assert calls[0][1]["client_id"] == CLIENT_ID
    assert spec.attempt_path.exists()
