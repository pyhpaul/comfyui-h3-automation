from __future__ import annotations

import base64
import json
import pytest

from comfy_orch.av_review.config import ConfigurationError, load_profile
from comfy_orch.av_review.media import MediaError, inspect_clip
from comfy_orch.av_review.provider import build_request, validate_assessment
from comfy_orch.av_review.service import ReviewService


@pytest.fixture
def project(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "av_review_profiles.toml").write_text(
        '[profiles.h3-av-review]\nprovider="google-gemini"\n'
        'base_url="https://generativelanguage.googleapis.com/v1beta"\n'
        'api_key_env="GEMINI_API_KEY"\nmodel="gemini-3.8-flash"\n'
    )
    return tmp_path


def make_clip(project):
    path = project / "runs/visual_qc/input/clip.mp4"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"fixture-video")
    return path


def probe_result():
    return {
        "format": {"duration": "6.4"},
        "streams": [{"codec_type": "video"}, {"codec_type": "audio"}],
    }


def assessment():
    return {
        "input_status": "AV_OBSERVED", "audio_status": "SPEECH_OBSERVED",
        "heard_text": "hello", "speech_segments": [{"start": 0.5, "end": 1.0, "text": "hello"}],
        "visible_events": ["a person waves"], "speaker_observations": [],
        "lip_sync_assessment": "UNVERIFIABLE", "limitations": ["test fixture"],
    }


def response(body=None, finish="STOP"):
    return {"candidates": [{"finishReason": finish, "content": {
        "parts": [{"text": json.dumps(body or assessment())}]}}]}


def test_profile_contains_no_key_and_reports_missing_environment(project):
    profile = load_profile(project, environ={})
    assert profile.model == "gemini-3.8-flash"
    with pytest.raises(ConfigurationError, match="GEMINI_API_KEY"):
        profile.get_key({})


def test_explicit_profile_overrides_environment_and_uses_configured_key_name(project):
    path = project / "config/av_review_profiles.toml"
    path.write_text(path.read_text() + '\n[profiles.other]\nprovider="google-gemini"\n'
                    'base_url="https://generativelanguage.googleapis.com/v1beta"\n'
                    'api_key_env="OTHER_API_KEY"\nmodel="gemini-4-argon"\n')
    profile = load_profile(project, "other", {"H3_AV_REVIEW_PROFILE": "absent"})
    assert profile.model == "gemini-4-argon"
    assert profile.get_key({"OTHER_API_KEY": "test-only"}) == "test-only"


def test_profile_file_override_missing_profile_and_missing_file(project):
    path = project / "config/av_review_profiles.toml"
    profile = load_profile(project, environ={"LLM_PROFILES_PATH": str(path)})
    assert profile.provider == "google-gemini"
    with pytest.raises(ConfigurationError, match="profile"):
        load_profile(project, "absent", {})
    with pytest.raises(ConfigurationError, match="file"):
        load_profile(project, environ={"H3_AV_REVIEW_PROFILES": str(project / "absent")})


@pytest.mark.parametrize("url", [
    "https://attacker.invalid/v1beta", "http://generativelanguage.googleapis.com/v1beta",
    "https://generativelanguage.googleapis.com/v1beta?key=secret",
    "https://user:pass@generativelanguage.googleapis.com/v1beta",
])
def test_profile_rejects_unapproved_key_destinations(project, url):
    path = project / "config/av_review_profiles.toml"
    path.write_text(path.read_text().replace("https://generativelanguage.googleapis.com/v1beta", url))
    with pytest.raises(ConfigurationError):
        load_profile(project, environ={})


def test_media_probe_is_hash_bound_and_has_no_network_protocol(project, monkeypatch):
    path = make_clip(project)
    calls = []

    def fake_probe(command, **kwargs):
        calls.append(command)
        return type("Completed", (), {"stdout": json.dumps(probe_result())})()

    monkeypatch.setattr("comfy_orch.av_review.media.subprocess.run", fake_probe)
    clip = inspect_clip(project, str(path))
    assert len(clip.sha256) == 64 and clip.duration == 6.4 and clip.has_audio
    assert calls[0][calls[0].index("-protocol_whitelist") + 1] == "file,pipe"


def test_media_rejects_outside_and_symlink_paths(project):
    outside = project / "outside.mp4"
    outside.write_bytes(b"private")
    root = project / "runs/visual_qc"
    root.mkdir(parents=True)
    (root / "escape.mp4").symlink_to(outside)
    for path in (outside, root / "escape.mp4"):
        with pytest.raises(MediaError, match="allowed"):
            inspect_clip(project, str(path))


def test_media_rejects_extension_and_size_before_probe(project):
    path = make_clip(project)
    path.rename(path.with_suffix(".txt"))
    with pytest.raises(MediaError, match="MP4"):
        inspect_clip(project, str(path.with_suffix(".txt")))
    with path.open("wb") as handle:
        handle.truncate(12 * 1024 * 1024 + 1)
    with pytest.raises(MediaError, match="size"):
        inspect_clip(project, str(path))


def test_request_includes_real_video_bytes_and_explicit_fps():
    payload = build_request(b"test-video", 8.0)
    part = payload["contents"][0]["parts"][0]
    assert base64.b64decode(part["inlineData"]["data"]) == b"test-video"
    assert part["inlineData"]["mimeType"] == "video/mp4"
    assert part["videoMetadata"]["fps"] == 8.0
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert "tools" not in payload


def test_zero_duration_and_out_of_bounds_segments_cannot_be_valid():
    body = assessment()
    body["speech_segments"] = [{"start": 1.0, "end": 1.0}, {"start": 3.0, "end": 9.0}]
    issues = validate_assessment(body, 6.4)
    assert any("duration" in issue for issue in issues)
    assert any("bounds" in issue for issue in issues)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "1"])
def test_invalid_timestamps_are_rejected(value):
    body = assessment()
    body["speech_segments"][0]["start"] = value
    assert validate_assessment(body, 6.4)


def test_silent_case_cannot_claim_spoken_content():
    body = assessment()
    body["audio_status"] = "SILENT"
    assert validate_assessment(body, 6.4)


def test_upload_needs_explicit_consent_and_key(project):
    service = ReviewService(project, environ={})
    denied = service.review_clip("ignored", allow_upload=False, expected_sha256="")
    assert denied["status"] == "UPLOAD_CONFIRMATION_REQUIRED"
    missing = service.status()
    assert missing["status"] == "API_KEY_MISSING" and not missing["live_av_verified"]
    with pytest.raises(ConfigurationError, match="GEMINI_API_KEY"):
        service.review_clip("ignored", allow_upload=True, expected_sha256="0" * 64)


def service_with_clip(project, monkeypatch, transport):
    path = make_clip(project)
    from comfy_orch.av_review.media import Clip
    import hashlib
    clip = Clip(path, hashlib.sha256(path.read_bytes()).hexdigest(), len(path.read_bytes()), 6.4, True, [])
    monkeypatch.setattr("comfy_orch.av_review.service.inspect_clip", lambda *_args: clip)
    return ReviewService(project, environ={"GEMINI_API_KEY": "test-secret"}, transport=transport), clip


def test_changed_hash_prevents_provider_call(project, monkeypatch):
    def forbidden(*args):
        pytest.fail("Provider must not be called")
    service, clip = service_with_clip(project, monkeypatch, forbidden)
    with pytest.raises(MediaError, match="hash"):
        service.review_clip(str(clip.path), True, "0" * 64)


def test_provisional_output_is_archived_without_key_or_base64(project, monkeypatch):
    calls = []
    def fake_provider(profile, key, payload):
        calls.append((profile, key, payload))
        return response()
    service, clip = service_with_clip(project, monkeypatch, fake_provider)
    report = service.review_clip(str(clip.path), True, clip.sha256)
    assert len(calls) == 1
    assert report["status"] == "MODEL_RESPONSE_RECORDED"
    assert report["may_issue_verdict"] is False and report["human_full_watch_count"] == 0
    assert report["effective_fps"] == "UNVERIFIED"
    directory = project / report["artifact_dir"]
    assert (directory / "provider-response.json").is_file()
    archived = "".join(p.read_text() for p in directory.glob("*.json"))
    assert "test-secret" not in archived
    assert base64.b64encode(b"fixture-video").decode() not in archived


def test_truncated_provider_output_is_never_complete(project, monkeypatch):
    service, clip = service_with_clip(project, monkeypatch, lambda *_: response(finish="MAX_TOKENS"))
    report = service.review_clip(str(clip.path), True, clip.sha256)
    assert report["status"] == "MODEL_RESPONSE_INVALID"
    assert any("MAX_TOKENS" in issue for issue in report["issues"])


def test_failed_request_does_not_retry_or_disclose_exception_secret(project, monkeypatch):
    from comfy_orch.av_review.provider import ProviderError
    calls = []
    def failing(*_):
        calls.append(1)
        raise ProviderError("upstream refused test-secret")
    service, clip = service_with_clip(project, monkeypatch, failing)
    report = service.review_clip(str(clip.path), True, clip.sha256)
    assert len(calls) == 1 and report["status"] == "REQUEST_FAILED_OUTCOME_UNKNOWN"
    assert "test-secret" not in json.dumps(report)


def test_sampling_budget_is_bounded(project, monkeypatch):
    service, clip = service_with_clip(project, monkeypatch, lambda *_: pytest.fail("No request expected"))
    with pytest.raises(MediaError, match="fps"):
        service.review_clip(str(clip.path), True, clip.sha256, fps=100)


@pytest.mark.parametrize("field", ["audio_status", "input_status", "lip_sync_assessment"])
def test_untrusted_enum_collections_are_invalid_not_crashes(field):
    body = assessment()
    body[field] = []
    assert validate_assessment(body, 6.4)


@pytest.mark.parametrize("raw", [
    {}, {"candidates": []}, {"candidates": [None]},
    {"candidates": [{"content": {"parts": ["not-an-object"]}}]},
])
def test_malformed_provider_response_is_incomplete(raw):
    from comfy_orch.av_review.provider import extract_assessment
    body, issues = extract_assessment(raw, 6.4)
    assert body is None and issues


def test_long_media_rejected(project, monkeypatch):
    path = make_clip(project)
    metadata = probe_result()
    metadata["format"]["duration"] = "31"
    monkeypatch.setattr("comfy_orch.av_review.media.subprocess.run", lambda *_a, **_k:
                        type("Completed", (), {"stdout": json.dumps(metadata)})())
    with pytest.raises(MediaError, match="30 seconds"):
        inspect_clip(project, str(path))


def test_artifact_directory_never_follows_outbound_symlink(project, monkeypatch):
    service, clip = service_with_clip(project, monkeypatch, lambda *_: pytest.fail("No upload"))
    outside = project / "unrelated"
    outside.mkdir()
    (project / "runs/visual_qc/av_mcp").symlink_to(outside, target_is_directory=True)
    with pytest.raises(MediaError, match="Output"):
        service.review_clip(str(clip.path), True, clip.sha256)


def test_json_artifacts_redact_even_provider_echoed_key(project, monkeypatch):
    body = assessment()
    body["limitations"] = ["unexpected test-secret echo"]
    service, clip = service_with_clip(project, monkeypatch, lambda *_: response(body))
    report = service.review_clip(str(clip.path), True, clip.sha256)
    assert "test-secret" not in json.dumps(report)
    directory = project / report["artifact_dir"]
    assert all("test-secret" not in p.read_text() for p in directory.glob("*.json"))


def test_relative_profile_path_is_relative_to_project_not_cwd(project, monkeypatch):
    monkeypatch.chdir(project.parent)
    assert load_profile(project, environ={"H3_AV_REVIEW_PROFILES": "config/av_review_profiles.toml"}).model


def test_modality_contradiction_is_not_accepted():
    body = assessment()
    body["input_status"] = "VISUAL_ONLY"
    assert validate_assessment(body, 6.4)


def test_provider_auth_is_header_only_and_redirects_disabled(project, monkeypatch):
    from comfy_orch.av_review.provider import send_request
    observed = []

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, _limit):
            return b'{"ok":true}'

    class Opener:
        def open(self, request, timeout):
            assert "test-secret" not in request.full_url
            assert request.headers["X-goog-api-key"] == "test-secret"
            assert timeout == 90
            observed.append(request)
            return Reply()

    def opener(handler):
        assert handler.redirect_request(None, None, 302, "", {}, "https://other.invalid") is None
        return Opener()

    monkeypatch.setattr("comfy_orch.av_review.provider.build_opener", opener)
    assert send_request(load_profile(project, environ={}), "test-secret", {}) == {"ok": True}
    assert len(observed) == 1
