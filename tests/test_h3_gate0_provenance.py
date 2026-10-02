"""Offline fault-injection tests for prompt-bound progress and output provenance."""

import asyncio
import copy
import json
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

import pytest
from aiohttp import web


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
from h3_gate0_outputs import (history_output_paths, inspect_latent, inspect_video, prefix_baseline,
                              prefix_inventory, validate_audio_timestamps, validate_av_alignment,
                              validate_video_timestamps)
from h3_gate0_handoff import publish_json_exclusive
from h3_gate0_progress import evaluate_progress
from h3_gate0_receipt import derive_receipt
from h3_gate0_telemetry import verify_telemetry
from h3_gate0_ws_observer import observe


PROMPT = "prompt-1"
CLIENT = "client-1"


def _event(message, index):
    return {"message": message, "received_monotonic_ns": index * 1_000_000_000,
            "received_at_utc": f"2026-09-26T00:00:{index:02d}+00:00"}


def _snapshot(state, value, maximum, prompt=PROMPT, node_id="226"):
    return {"type": "progress_state", "data": {"prompt_id": prompt,
            "nodes": {"226": {"prompt_id": prompt, "node_id": node_id,
                              "state": state, "value": value, "max": maximum}}}}


def _history():
    return {PROMPT: {"prompt": [0, PROMPT, {}, {"client_id": CLIENT}],
                     "status": {"status_str": "success", "completed": True,
                                "messages": [["execution_start", {"prompt_id": PROMPT}],
                                             ["execution_cached", {"prompt_id": PROMPT, "nodes": []}],
                                             ["execution_success", {"prompt_id": PROMPT}]]}}}


def _trace():
    messages = [{"type": "status", "data": {"sid": CLIENT}},
                _snapshot("running", 0, 1)]
    messages.extend(_snapshot("running", step, 12) for step in range(1, 13))
    messages.append(_snapshot("finished", 12, 12))
    messages.append({"type": "executing", "data": {"prompt_id": PROMPT, "node": None}})
    return {"client_id": CLIENT, "events": [_event(message, index)
            for index, message in enumerate(messages)], "closed_reason": "terminal"}


def test_complete_progress_and_repeated_snapshot():
    trace = _trace()
    result = evaluate_progress(trace, _history(), PROMPT)
    assert result.state == "derived_verified"
    assert result.steps == tuple(range(1, 13))
    assert result.observed_node_interval_s == 13
    trace["events"].insert(4, copy.deepcopy(trace["events"][3]))
    for index, event in enumerate(trace["events"]):
        event["received_monotonic_ns"] = index * 1_000_000_000
    assert evaluate_progress(trace, _history(), PROMPT).state == "derived_verified"
    trace = _trace()
    trace["events"].insert(-1, copy.deepcopy(trace["events"][-2]))
    for index, event in enumerate(trace["events"]):
        event["received_monotonic_ns"] = index * 1_000_000_000
    assert evaluate_progress(trace, _history(), PROMPT).state == "derived_verified"


def test_late_prompt_id_terminal_allows_reconciled_trailing_status_only():
    trace = _trace()
    terminal_index = len(trace["events"]) - 1
    trace["events"].append(_event({"type": "status", "data": {"sid": CLIENT}},
                                  terminal_index + 1))
    trace["reconciliation"] = {"method": "late_prompt_id",
                               "terminal_event_index": terminal_index}
    assert evaluate_progress(trace, _history(), PROMPT).state == "derived_verified"
    trace["reconciliation"]["terminal_event_index"] = terminal_index - 1
    assert evaluate_progress(trace, _history(), PROMPT).state == "sampler_unknown"
    trace["reconciliation"]["terminal_event_index"] = terminal_index
    trace["events"][-1]["message"] = _snapshot("finished", 12, 12)
    assert evaluate_progress(trace, _history(), PROMPT).state == "sampler_unknown"


def _duplicate_terminal(trace):
    trace["events"].insert(-1, copy.deepcopy(trace["events"][-1]))
    for index, event in enumerate(trace["events"]):
        event["received_monotonic_ns"] = index * 1_000_000_000


@pytest.mark.parametrize("change", [
    lambda t: t["events"].pop(5),
    lambda t: t["events"][6]["message"]["data"]["nodes"]["226"].update(value=3),
    lambda t: t["events"][6]["message"]["data"]["nodes"]["226"].update(max=11),
    lambda t: t["events"][6]["message"]["data"].update(prompt_id="foreign"),
    lambda t: t["events"][6]["message"]["data"]["nodes"]["226"].update(node_id="999"),
    lambda t: t.update(closed_reason="disconnected"),
    _duplicate_terminal,
    lambda t: t["events"][0]["message"]["data"].update(sid="foreign"),
    lambda t: t["events"][3].update(received_at_utc="not-a-time"),
    lambda t: t["events"][3].update(received_at_utc="2026-09-26T00:00:00+00:00"),
    lambda t: t["events"][3].update(received_monotonic_ns=2_000_000_000),
])
def test_progress_faults_are_unknown(change):
    trace = _trace()
    change(trace)
    assert evaluate_progress(trace, _history(), PROMPT).state == "sampler_unknown"


def test_wrong_history_client_or_cached_sampler_is_unknown():
    history = _history()
    history[PROMPT]["prompt"][3]["client_id"] = "foreign"
    assert evaluate_progress(_trace(), history, PROMPT).state == "sampler_unknown"
    history = _history()
    history[PROMPT]["status"]["messages"][1][1]["nodes"] = ["226"]
    assert evaluate_progress(_trace(), history, PROMPT).state == "sampler_unknown"


def test_receipt_distinguishes_history_wall_from_ws_receive_interval(tmp_path):
    graph = {"226": {"class_type": "Sampler"}}
    history = _history()
    history[PROMPT]["prompt"][2] = graph
    history[PROMPT]["status"]["messages"][0][1]["timestamp"] = 1000
    history[PROMPT]["status"]["messages"][2][1]["timestamp"] = 66000
    parent = tmp_path / "parent.safetensors"
    parent.write_bytes(b"parent")
    unknown = derive_receipt(history, PROMPT, graph, parent)
    assert unknown["server_wall_s"] == {"tier": "derived_verified", "value": 65.0}
    assert unknown["sampler_steps"]["tier"] == "unknown"
    observed = derive_receipt(history, PROMPT, graph, parent, _trace())
    assert observed["observed_node_interval_s"]["value"] == 13
    assert observed["sampler_wall_s"]["tier"] == "unknown"
    with pytest.raises(ValueError, match="submitted graph"):
        derive_receipt(history, PROMPT, {}, parent)


def _output_history(root):
    video_prefix, latent_prefix = "gate/run-video", "gate/run-latent"
    (root / "gate").mkdir(parents=True)
    video_baseline = prefix_baseline(root, video_prefix)
    latent_baseline = prefix_baseline(root, latent_prefix)
    start_ms = int(time.time() * 1000)
    video = root / f"{video_prefix}_00001-audio.mp4"
    latent = root / f"{latent_prefix}_00001.safetensors"
    video.write_bytes(b"video fixture")
    latent.write_bytes(b"latent fixture")
    history = {PROMPT: {"prompt": [0, PROMPT, {
        "264": {"inputs": {"filename_prefix": video_prefix}},
        "400": {"inputs": {"filename_prefix": latent_prefix}},
        "405": {"inputs": {"source": ["400", 0]}}}],
        "status": {"status_str": "success", "completed": True,
                   "messages": [["execution_start", {"prompt_id": PROMPT,
                                                     "timestamp": start_ms}]]},
        "outputs": {"264": {"gifs": [{"fullpath": str(video), "filename": video.name,
                                        "type": "output", "format": "video/h264-mp4"}]},
                    "405": {"text": [str(latent)]}}}}
    return history, video_prefix, latent_prefix, video, latent, video_baseline, latent_baseline


def test_history_output_binding_and_preexisting_prefix(tmp_path):
    history, video_prefix, latent_prefix, video, latent, video_baseline, latent_baseline = _output_history(tmp_path)
    assert history_output_paths(history, PROMPT, tmp_path, video_prefix, latent_prefix,
                                video_baseline, latent_baseline) == (video, latent)
    assert prefix_inventory(tmp_path, video_prefix) == [str(video.relative_to(tmp_path))]
    with pytest.raises(ValueError, match="occupied"):
        occupied = dict(video_baseline, files=["old.mp4"])
        history_output_paths(history, PROMPT, tmp_path, video_prefix, latent_prefix,
                             occupied, latent_baseline)
    history[PROMPT]["outputs"]["405"]["text"] = [str(tmp_path / "foreign.safetensors")]
    with pytest.raises((ValueError, FileNotFoundError)):
        history_output_paths(history, PROMPT, tmp_path, video_prefix, latent_prefix,
                             video_baseline, latent_baseline)


def test_history_output_symlink_is_rejected(tmp_path):
    history, video_prefix, latent_prefix, video, _, video_baseline, latent_baseline = _output_history(tmp_path)
    alias = video.with_name(video_prefix.split("/")[-1] + "_00002-audio.mp4")
    alias.symlink_to(video)
    history[PROMPT]["outputs"]["264"]["gifs"][0].update(fullpath=str(alias), filename=alias.name)
    with pytest.raises(ValueError, match="symlink"):
        history_output_paths(history, PROMPT, tmp_path, video_prefix, latent_prefix,
                             video_baseline, latent_baseline)


def test_history_output_same_prefix_subdirectory_is_rejected(tmp_path):
    history, video_prefix, latent_prefix, video, _, video_baseline, latent_baseline = _output_history(tmp_path)
    nested = video.parent / "run-video_extra" / video.name
    nested.parent.mkdir()
    nested.write_bytes(video.read_bytes())
    history[PROMPT]["outputs"]["264"]["gifs"][0].update(fullpath=str(nested))
    with pytest.raises(ValueError, match="foreign prefix"):
        history_output_paths(history, PROMPT, tmp_path, video_prefix, latent_prefix,
                             video_baseline, latent_baseline)


def test_latent_header_shape_and_finite(tmp_path):
    path = tmp_path / "tiny.safetensors"
    header = {"audio": {"dtype": "F32", "shape": [2], "data_offsets": [0, 8]}}
    encoded = json.dumps(header).encode()
    path.write_bytes(struct.pack("<Q", len(encoded)) + encoded + struct.pack("<ff", 1, 2))
    assert inspect_latent(path, {"audio": [2]})["finite"] is True
    with pytest.raises(ValueError, match="layout"):
        inspect_latent(path, {"audio": [3]})
    path.write_bytes(struct.pack("<Q", len(encoded)) + encoded + struct.pack("<ff", 1, float("nan")))
    with pytest.raises(ValueError, match="nonfinite"):
        inspect_latent(path, {"audio": [2]})


def test_telemetry_uuid_and_coverage(tmp_path):
    path = tmp_path / "samples.jsonl"
    samples = [{"at_utc": f"2026-09-26T00:00:{step:02d}+00:00",
                "gpu_uuid": "GPU-fixture", "device_index": 0,
                "utilization_pct": 90, "vram_mib": 30000} for step in (0, 5, 10)]
    path.write_text("\n".join(json.dumps(sample) for sample in samples))
    result = verify_telemetry(path, "GPU-fixture", 0,
                              samples[0]["at_utc"], samples[-1]["at_utc"])
    assert result["sensor_values"]["tier"] == "reported_only"
    with pytest.raises(ValueError, match="UUID"):
        verify_telemetry(path, "GPU-foreign", 0,
                         samples[0]["at_utc"], samples[-1]["at_utc"])


def test_telemetry_sparse_edges_are_not_coverage(tmp_path):
    path = tmp_path / "sparse.jsonl"
    samples = [{"at_utc": f"2026-09-26T00:00:{second:02d}+00:00",
                "gpu_uuid": "GPU-fixture", "device_index": 0,
                "utilization_pct": 90, "vram_mib": 30000}
               for second in (9, 11)]
    path.write_text("\n".join(json.dumps(sample) for sample in samples))
    with pytest.raises(ValueError, match="cover"):
        verify_telemetry(path, "GPU-fixture", 0,
                         "2026-09-26T00:00:00+00:00",
                         "2026-09-26T00:00:20+00:00")


def test_telemetry_non_object_line_is_rejected(tmp_path):
    path = tmp_path / "malformed.jsonl"
    path.write_text('1\n{"at_utc":"2026-09-26T00:00:10+00:00"}')
    with pytest.raises(ValueError, match="not an object"):
        verify_telemetry(path, "GPU-fixture", 0,
                         "2026-09-26T00:00:00+00:00",
                         "2026-09-26T00:00:10+00:00")


def test_wrong_media_dimensions_rejected(tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg/ffprobe unavailable")
    path = tmp_path / "wrong.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi",
                    "-i", "color=c=black:s=320x240:r=24:d=0.5", "-f", "lavfi",
                    "-i", "anullsrc=r=32000:cl=mono", "-t", "0.5", "-c:v", "libx264",
                    "-c:a", "aac", str(path)], check=True, timeout=30)
    with pytest.raises(ValueError, match="dimensions"):
        inspect_video(path)


def test_media_timeline_shift_rejected():
    timeline = {"stream": {"time_base": "1/24"},
                "frames": [{"best_effort_timestamp": str(index)} for index in range(306)]}
    validate_video_timestamps(timeline)
    shifted = copy.deepcopy(timeline)
    shifted["frames"][20]["best_effort_timestamp"] = "22"
    with pytest.raises(ValueError, match="timeline"):
        validate_video_timestamps(shifted)


def test_whole_audio_shift_and_regression_rejected():
    video = {"start_time": "0.000000", "duration": "12.750000"}
    audio = {"start_time": "0.000000", "duration": "12.736000"}
    validate_av_alignment(video, audio)
    audio["start_time"] = "0.250000"
    with pytest.raises(ValueError, match="time-shifted"):
        validate_av_alignment(video, audio)
    audio["start_time"] = "nan"
    with pytest.raises(ValueError, match="time-shifted"):
        validate_av_alignment(video, audio)
    with pytest.raises(ValueError, match="timeline"):
        validate_audio_timestamps({"stream": {"sample_rate": "32000", "time_base": "1/32000"},
                                   "frames": [
            {"best_effort_timestamp": "0", "nb_samples": 1024},
            {"best_effort_timestamp": "1024", "nb_samples": 1024},
            {"best_effort_timestamp": "1024", "nb_samples": 1024}]})


def test_audio_internal_gap_is_rejected():
    timeline = {"stream": {"sample_rate": "32000", "time_base": "1/32000"},
                "frames": [{"best_effort_timestamp": tick, "nb_samples": 1024}
                           for tick in (0, 1024, 2048)]}
    validate_audio_timestamps(timeline)
    timeline["frames"][2]["best_effort_timestamp"] = 4096
    with pytest.raises(ValueError, match="internal gap"):
        validate_audio_timestamps(timeline)


def test_observer_handshake_and_terminal_with_local_ws(tmp_path):
    async def scenario():
        app = web.Application()

        async def ws_handler(request):
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            client_id = request.query["clientId"]
            await ws.send_json({"type": "status", "data": {"sid": client_id}})
            await ws.send_bytes(b"preview-fixture")
            while not prompt_file.exists():
                await asyncio.sleep(0.01)
            await ws.send_json({"type": "executing", "data": {"prompt_id": PROMPT, "node": None}})
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
                                               ready_file, trace_file, prompt_file, 2,
                                               run_id="run-fixture", graph_sha256="a" * 64))
            for _ in range(100):
                if ready_file.exists():
                    break
                await asyncio.sleep(0.01)
            assert ready_file.exists()
            publish_json_exclusive(prompt_file, {"run_id": "run-fixture",
                                                "client_id": json.loads(ready_file.read_text())["client_id"],
                                                "prompt_id": PROMPT})
            trace = await task
            assert trace["closed_reason"] == "terminal"
            assert trace["events"][1]["message"]["type"] == "binary_frame"
            assert json.loads(ready_file.read_text())["client_id"] == trace["client_id"]
            assert json.loads(trace_file.read_text()) == trace
        finally:
            await runner.cleanup()

    ready_file = tmp_path / "ready.json"
    trace_file = tmp_path / "trace.json"
    prompt_file = tmp_path / "prompt-id.txt"
    asyncio.run(scenario())


def test_observer_rejects_wrong_client_without_readiness(tmp_path):
    async def scenario():
        app = web.Application()

        async def ws_handler(request):
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            await ws.send_json({"type": "status", "data": {"sid": "foreign"}})
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
                                  tmp_path / "prompt.txt", 2,
                                  run_id="run-fixture", graph_sha256="a" * 64)
            assert trace["closed_reason"] == "handshake_mismatch"
            assert not (tmp_path / "ready.json").exists()
        finally:
            await runner.cleanup()

    asyncio.run(scenario())
