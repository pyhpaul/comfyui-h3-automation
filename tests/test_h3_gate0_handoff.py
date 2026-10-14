"""No-network tests for one-shot prompt-ID handoff and observer races."""

import asyncio
import hashlib
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from aiohttp import web


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
from h3_gate0_handoff import HandoffSpec, mock_submit_once, publish_json_exclusive
import h3_gate0_handoff as handoff
import h3_gate0_ws_observer as observer
from h3_gate0_ws_observer import observe


def _fixture(tmp_path):
    graph_path = tmp_path / "graph.json"
    graph_path.write_text('{"226":{"class_type":"Sampler"}}')
    graph_sha = hashlib.sha256(graph_path.read_bytes()).hexdigest()
    run_dir = tmp_path / "run-one"
    run_dir.mkdir()
    spec = HandoffSpec("run-one", graph_sha, "http://fixture.invalid",
                       graph_path, run_dir)
    publish_json_exclusive(spec.ready_path, {
        "run_id": spec.run_id, "graph_sha256": graph_sha,
        "endpoint": spec.endpoint, "observer_state": "connected",
        "client_id": "11111111-1111-4111-8111-111111111111",
        "observer_pid": os.getpid(),
        "ready_at_utc": datetime.now(timezone.utc).isoformat()})
    return spec


def test_handoff_is_at_most_once(tmp_path):
    spec = _fixture(tmp_path)
    calls = []

    def transport(endpoint, payload):
        calls.append((endpoint, payload))
        return {"prompt_id": "prompt-one"}

    assert mock_submit_once(spec, transport) == "prompt-one"
    assert len(calls) == 1
    assert calls[0][1]["client_id"] == "11111111-1111-4111-8111-111111111111"
    assert json.loads(spec.prompt_id_path.read_text())["attempt_id"] == \
        json.loads(spec.attempt_path.read_text())["attempt_id"]
    with pytest.raises(ValueError, match="already published"):
        mock_submit_once(spec, transport)
    assert len(calls) == 1


def test_competing_claims_call_mock_transport_once(tmp_path):
    spec = _fixture(tmp_path)
    barrier = threading.Barrier(2)
    calls = []

    def run():
        barrier.wait()
        try:
            return mock_submit_once(spec, lambda endpoint, payload: (
                calls.append(payload) or {"prompt_id": "prompt-one"}))
        except (FileExistsError, ValueError):
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert sorted(results) == ["prompt-one", "rejected"]
    assert len(calls) == 1


def test_response_loss_consumes_attempt(tmp_path):
    spec = _fixture(tmp_path)
    calls = []

    def lost(endpoint, payload):
        calls.append(payload)
        raise TimeoutError("response lost after possible submission")

    with pytest.raises(TimeoutError):
        mock_submit_once(spec, lost)
    assert spec.attempt_path.exists()
    assert not spec.prompt_id_path.exists()
    with pytest.raises(FileExistsError):
        equivalent = HandoffSpec(spec.run_id, spec.graph_sha256, spec.endpoint,
                                 spec.graph_path, spec.run_dir)
        mock_submit_once(equivalent, lost)
    assert len(calls) == 1


def test_attempt_and_prompt_paths_are_derived_from_run_directory(tmp_path):
    spec = _fixture(tmp_path)
    assert spec.attempt_path == spec.ready_path.parent / "attempt.json"
    assert spec.prompt_id_path == spec.ready_path.parent / "prompt.json"
    with pytest.raises(TypeError):
        HandoffSpec(spec.run_id, spec.graph_sha256, spec.endpoint,
                    spec.graph_path, spec.run_dir, attempt_path=tmp_path / "alternate.json")


def test_wrong_run_namespace_or_endpoint_cannot_submit(tmp_path):
    spec = _fixture(tmp_path)
    calls = []
    invalid = HandoffSpec(spec.run_id, spec.graph_sha256, spec.endpoint,
                          spec.graph_path, tmp_path / "alternate")
    with pytest.raises(ValueError, match="namespace"):
        mock_submit_once(invalid, lambda endpoint, payload: calls.append(payload))
    invalid = HandoffSpec(spec.run_id, spec.graph_sha256, "http://fixture.invalid/path",
                          spec.graph_path, spec.run_dir)
    with pytest.raises(ValueError, match="endpoint"):
        mock_submit_once(invalid, lambda endpoint, payload: calls.append(payload))
    assert calls == []


def test_payload_uses_exact_hash_checked_graph_snapshot(tmp_path, monkeypatch):
    spec = _fixture(tmp_path)
    original_ready = handoff._load_ready
    submitted = []

    def mutate_after_graph_read(current):
        ready = original_ready(current)
        current.graph_path.write_text('{"226":{"class_type":"Changed"}}')
        return ready

    monkeypatch.setattr(handoff, "_load_ready", mutate_after_graph_read)
    assert mock_submit_once(spec, lambda endpoint, payload: (
        submitted.append(payload["prompt"]) or {"prompt_id": "prompt-one"})) == "prompt-one"
    assert submitted == [{"226": {"class_type": "Sampler"}}]


def test_prompt_publication_failure_does_not_release_attempt(tmp_path):
    spec = _fixture(tmp_path)
    calls = []

    def transport(endpoint, payload):
        calls.append(payload)
        spec.prompt_id_path.write_text("occupied")
        return {"prompt_id": "prompt-one"}

    with pytest.raises(FileExistsError):
        mock_submit_once(spec, transport)
    assert spec.attempt_path.exists()
    assert len(calls) == 1


def test_stale_or_closed_observer_cannot_submit(tmp_path):
    spec = _fixture(tmp_path)
    ready = json.loads(spec.ready_path.read_text())
    ready["ready_at_utc"] = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    spec.ready_path.write_text(json.dumps(ready))
    with pytest.raises(ValueError, match="stale"):
        mock_submit_once(spec, lambda endpoint, payload: {"prompt_id": "p"})
    ready["ready_at_utc"] = datetime.now(timezone.utc).isoformat()
    spec.ready_path.write_text(json.dumps(ready))
    publish_json_exclusive(spec.ready_path.with_suffix(".closed.json"), {"reason": "disconnected"})
    with pytest.raises(ValueError, match="closed"):
        mock_submit_once(spec, lambda endpoint, payload: {"prompt_id": "p"})
    assert not spec.attempt_path.exists()


def test_observer_closing_after_claim_prevents_transport(tmp_path, monkeypatch):
    spec = _fixture(tmp_path)
    original_claim = handoff._claim_attempt

    def claim_then_close(current, client_id):
        attempt_id = original_claim(current, client_id)
        publish_json_exclusive(spec.ready_path.with_suffix(".closed.json"),
                               {"reason": "disconnected"})
        return attempt_id

    monkeypatch.setattr(handoff, "_claim_attempt", claim_then_close)
    calls = []
    with pytest.raises(ValueError, match="closed before transport"):
        mock_submit_once(spec, lambda endpoint, payload: calls.append(payload))
    assert spec.attempt_path.exists()
    assert calls == []


def test_late_prompt_id_reconciles_without_new_ws_message(tmp_path):
    async def scenario():
        sent_terminal = asyncio.Event()
        app = web.Application()

        async def ws_handler(request):
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            await ws.send_json({"type": "status", "data": {"sid": request.query["clientId"]}})
            await ws.send_json({"type": "executing", "data": {"prompt_id": "prompt-one", "node": None}})
            sent_terminal.set()
            await asyncio.sleep(1)
            await ws.close()
            return ws

        app.router.add_get("/ws", ws_handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            task = asyncio.create_task(observe(f"ws://127.0.0.1:{port}/ws",
                                               ready, trace_file, prompt_file, 2,
                                               run_id="run-one", graph_sha256="a" * 64))
            await sent_terminal.wait()
            while not ready.exists():
                await asyncio.sleep(0.01)
            await asyncio.sleep(0.05)
            publish_json_exclusive(prompt_file, {"run_id": "run-one",
                                                 "client_id": json.loads(ready.read_text())["client_id"],
                                                 "prompt_id": "prompt-one"})
            trace = await task
            assert trace["closed_reason"] == "terminal"
            assert trace["reconciliation"]["method"] == "late_prompt_id"
            assert len(trace["events"]) == 2
        finally:
            await runner.cleanup()

    ready = tmp_path / "ready.json"
    trace_file = tmp_path / "trace.json"
    prompt_file = tmp_path / "prompt.json"
    asyncio.run(scenario())


def test_disconnect_after_terminal_before_prompt_id_stays_disconnected(tmp_path):
    async def scenario():
        app = web.Application()

        async def ws_handler(request):
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            await ws.send_json({"type": "status", "data": {"sid": request.query["clientId"]}})
            await ws.send_json({"type": "executing", "data": {"prompt_id": "prompt-one", "node": None}})
            await ws.close()
            return ws

        app.router.add_get("/ws", ws_handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            trace = await observe(f"ws://127.0.0.1:{port}/ws",
                                  tmp_path / "ready.json", tmp_path / "trace.json",
                                  tmp_path / "prompt.json", 2,
                                  run_id="run-one", graph_sha256="a" * 64)
            assert trace["closed_reason"] == "disconnected"
        finally:
            await runner.cleanup()

    asyncio.run(scenario())


def test_observer_deadline_includes_connection_handshake(tmp_path):
    async def scenario():
        app = web.Application()

        async def delayed_ws(request):
            await asyncio.sleep(0.5)
            return web.Response(text="late")

        app.router.add_get("/ws", delayed_ws)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            trace = await observe(f"ws://127.0.0.1:{port}/ws",
                                  tmp_path / "ready.json", tmp_path / "trace.json",
                                  tmp_path / "prompt.json", 0.1,
                                  run_id="run-one", graph_sha256="a" * 64)
            assert trace["closed_reason"] == "timeout"
            assert not (tmp_path / "ready.json").exists()
        finally:
            await runner.cleanup()

    asyncio.run(scenario())


def test_observer_bounds_cumulative_event_bytes(tmp_path, monkeypatch):
    async def scenario():
        app = web.Application()

        async def ws_handler(request):
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            await ws.send_json({"type": "status", "data": {"sid": request.query["clientId"]}})
            await ws.send_bytes(b"x" * 256)
            await asyncio.sleep(0.2)
            await ws.close()
            return ws

        app.router.add_get("/ws", ws_handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            trace = await observe(f"ws://127.0.0.1:{port}/ws",
                                  tmp_path / "ready.json", tmp_path / "trace.json",
                                  tmp_path / "prompt.json", 1,
                                  run_id="run-one", graph_sha256="a" * 64)
            assert trace["closed_reason"] == "event_limit"
            assert len(trace["events"]) == 1
            assert (tmp_path / "ready.json").exists()
        finally:
            await runner.cleanup()

    monkeypatch.setattr(observer, "MAX_OBSERVED_BYTES", 128)
    asyncio.run(scenario())
