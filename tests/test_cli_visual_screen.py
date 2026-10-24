import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from comfy_orch.av_review.cli_screen import decode_final, image_read_coverage, run_cli, validate_screen_answer
from comfy_orch.av_review.frames import Frame
from comfy_orch.av_review.contact_sheets import build_contact_sheets
from comfy_orch.av_review.media import MediaError


def test_navigation_sheets_preserve_originals_and_map_every_frame(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    frames = []
    for i in range(7):
        path = tmp_path / f"{i}.jpg"
        Image.new("RGB", (160, 240), "red").save(path)
        frames.append(Frame(path, i*0.25, hashlib.sha256(path.read_bytes()).hexdigest()))
    sheets = build_contact_sheets(frames, tmp_path / "sheets")
    assert len(sheets) == 2
    assert [c["frame_id"] for s in sheets for c in s["cells"]] == [f"F{i:03d}" for i in range(1, 8)]
    assert [c["source_time"] for s in sheets for c in s["cells"]] == [i*0.25 for i in range(7)]
    assert all(hashlib.sha256(f.path.read_bytes()).hexdigest() == f.sha256 for f in frames)
    frames[0].path.write_bytes(b"modified")
    with pytest.raises(MediaError, match="hash"):
        build_contact_sheets(frames, tmp_path / "changed")


def test_read_coverage_uses_tool_blobs_not_claims(tmp_path):
    path = str(tmp_path / "frame.jpg")
    def event(success):
        return {"type": "tool_call", "subtype": "completed", "tool_call": {"readToolCall": {
            "args": {"path": path}, "result": {"success": success}}}}
    assert image_read_coverage([event({})], {path})["completed_image_reads"] == 0
    assert image_read_coverage([event({"dataBlobId": "fixture"})], {path})["completed_image_reads"] == 1


def test_non_read_tools_not_allowed():
    event = {"type": "tool_call", "subtype": "completed", "tool_call": {"shellToolCall": {}}}
    assert image_read_coverage([event], set())["unexpected"]


@pytest.mark.parametrize("events", [[], [{"type": "result", "is_error": True}],
                                    [{"type": "result", "result": "no json"}]])
def test_missing_cli_answer_not_success(events):
    with pytest.raises(ValueError):
        decode_final(events)


def test_final_json_can_follow_cli_commentary():
    answer = {"audio_status": "AUDIO_UNAVAILABLE"}
    assert decode_final([{"type": "result", "result": "Reading.```json\n"+json.dumps(answer)+"\n```"}]) == answer


def test_unknown_model_frame_ids_are_rejected():
    body = {"unit": "EP01-U01", "visible_events": [], "mouth_visibility_notes": [],
            "suspects": [], "detail_frame_ids": ["F999"], "limitations": []}
    assert validate_screen_answer(body, "EP01-U01", {"F001"})
    body["detail_frame_ids"] = ["F001"]
    assert not validate_screen_answer(body, "EP01-U01", {"F001"})


def test_timeout_stops_owned_process_group_and_does_not_retry(tmp_path, monkeypatch):
    import signal
    import subprocess
    waits = []
    kills = []

    class Process:
        pid = 12345

        def wait(self, timeout=None):
            waits.append(timeout)
            if len(waits) == 1:
                raise subprocess.TimeoutExpired("fixture-cli", timeout)
            return -15

    calls = []
    def popen(*args, **kwargs):
        calls.append(kwargs)
        return Process()
    monkeypatch.setattr("comfy_orch.av_review.cli_screen.subprocess.Popen", popen)
    monkeypatch.setattr("comfy_orch.av_review.cli_screen.os.killpg", lambda pid, sig: kills.append((pid, sig)))
    report = run_cli(tmp_path, tmp_path / "attempt", "fixture", [], timeout=1, model="grok-4.7-low")
    assert len(calls) == 1 and calls[0]["start_new_session"] is True
    assert kills == [(12345, signal.SIGTERM)]
    assert report["status"] == "SCREEN_INCOMPLETE"
    assert report["exit_code"] == "TIMEOUT_NO_AUTOMATIC_RETRY"


def test_detail_prioritizes_anatomy_over_low_value_blocking():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("detail_qc", root / "scripts/ops/detail_visual_qc_screen.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    answer = {"suspects": [
        {"category": "composition_constraint", "detail_frame_ids": [f"F{i:03d}" for i in range(1, 7)]},
        {"category": "anatomy", "detail_frame_ids": ["F007"]}], "detail_frame_ids": []}
    selected, deferred = module.choose_frames(answer, {f"F{i:03d}" for i in range(1, 8)}, [])
    assert selected[0] == "F007"
    assert len(selected) == 6 and deferred == ["F006"]
