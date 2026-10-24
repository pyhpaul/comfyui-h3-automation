import json
import shutil
import subprocess

import pytest

from comfy_orch.av_review.config import ConfigurationError, Profile, load_profile
from comfy_orch.av_review.frames import Frame, extract_frames, validate_frame_budget
from comfy_orch.av_review.grok_provider import build_grok_request, extract_grok_assessment
from comfy_orch.av_review.media import MediaError, inspect_clip
from comfy_orch.av_review.service import ReviewService


@pytest.mark.parametrize("fps", [True, 0, 9, float("nan"), "4"])
def test_invalid_frame_fps(fps):
    with pytest.raises(MediaError):
        validate_frame_budget(fps, 6.4)


def test_frame_count_budget():
    with pytest.raises(MediaError):
        validate_frame_budget(4, 30)


def test_grok_profile_is_explicit_not_default(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "av_review_profiles.toml").write_text(
        '[profiles.h3-grok-screen]\nprovider="xai-grok"\nbase_url="https://api.x.ai/v1"\n'
        'api_key_env="XAI_API_KEY"\nmodel="grok-4.7"\n')
    profile = load_profile(tmp_path, "h3-grok-screen", {})
    assert profile.get_key({"XAI_API_KEY": "fixture"}) == "fixture"
    with pytest.raises(ConfigurationError):
        load_profile(tmp_path, environ={})


def test_grok_visual_payload_has_no_audio_or_search(tmp_path):
    import hashlib
    path = tmp_path / "frame.jpg"
    path.write_bytes(b"fixture-image")
    frame = Frame(path, 0.25, hashlib.sha256(path.read_bytes()).hexdigest())
    profile = Profile("test", "xai-grok", "https://api.x.ai/v1", "XAI_API_KEY", "grok-4.7")
    payload = build_grok_request(profile, [frame])
    assert payload["store"] is False and payload["tools"] == []
    assert payload["input"][0]["content"][-1]["type"] == "input_image"
    assert "0.250000" in json.dumps(payload)
    path.write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="changed"):
        build_grok_request(profile, [frame])


def visual_answer():
    return {"input_status": "VISUAL_ONLY", "audio_status": "AUDIO_UNAVAILABLE", "heard_text": None,
            "speech_segments": [], "visible_events": [], "speaker_observations": [],
            "lip_sync_assessment": "UNVERIFIABLE", "limitations": ["no audio"]}


def wrapped(answer, status="completed"):
    return {"status": status, "output": [{"type": "message", "content": [
        {"type": "output_text", "text": json.dumps(answer)}]}]}


def test_grok_response_cannot_promote_stills_to_av():
    answer, issues = extract_grok_assessment(wrapped(visual_answer()), 6.4)
    assert answer and not issues
    bad = visual_answer()
    bad["lip_sync_assessment"] = "NORMAL_PROVISIONAL"
    assert extract_grok_assessment(wrapped(bad), 6.4)[1]
    assert extract_grok_assessment(wrapped(visual_answer(), "incomplete"), 6.4)[1]


@pytest.mark.parametrize("raw", [{}, {"output": [None]}, {"output": [{"type": "message", "content": [None]}]}])
def test_bad_grok_response_is_invalid(raw):
    assert extract_grok_assessment(raw, 6.4)[1]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")
def test_local_frames_work_without_credentials_or_provider(tmp_path):
    path = tmp_path / "runs/visual_qc/source.mp4"
    path.parent.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-f", "lavfi", "-i",
                    "testsrc2=size=160x240:rate=24:duration=2", "-c:v", "libx264", str(path)],
                   check=True, capture_output=True)
    def forbidden(*args):
        pytest.fail("Local preparation must never call a provider")
    service = ReviewService(tmp_path, environ={}, transport=forbidden)
    clip = inspect_clip(tmp_path, str(path))
    with pytest.raises(MediaError, match="hash"):
        service.prepare_visual_clip(str(path), "wrong")
    report = service.prepare_visual_clip(str(path), clip.sha256, fps=4)
    assert report["uploaded"] is False and report["audio_included"] is False
    assert len(report["frames"]) == 8
    assert [f["time_seconds"] for f in report["frames"]] == [i/4 for i in range(8)]
    assert report["may_issue_verdict"] is False
    assert inspect_clip(tmp_path, str(path)).sha256 == clip.sha256
    window = tmp_path / "runs/visual_qc/native-window"
    window.mkdir()
    frames = extract_frames(clip, window, 4, start=0.5, end=1.25, native_resolution=True)
    assert [frame.time for frame in frames] == [0.5, 0.75, 1.0]
    metadata = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(frames[0].path)],
        check=True, capture_output=True, text=True).stdout)
    assert metadata["streams"][0]["width"] == 160
    assert metadata["streams"][0]["height"] == 240
    with pytest.raises(MediaError, match="window"):
        extract_frames(clip, tmp_path, 4, start=2, end=1)
    directory = tmp_path / "runs/visual_qc/changed-source"
    directory.mkdir()
    path.write_bytes(b"modified")
    with pytest.raises(MediaError, match="hash"):
        extract_frames(clip, directory, 4)
