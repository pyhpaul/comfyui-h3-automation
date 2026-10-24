from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from .config import ConfigurationError, load_profile
from .media import MAX_BYTES, MediaError, inspect_clip, validate_sampling
from .frames import extract_frames, validate_frame_budget
from .provider import PROMPT, ProviderError, build_request, extract_assessment, send_request


class ReviewService:
    def __init__(self, project_root: Path, environ: Mapping[str, str] | None = None,
                 transport: Callable | None = None):
        self.root = project_root.resolve()
        self.environ = os.environ if environ is None else environ
        self.transport = transport or send_request

    def status(self) -> dict:
        base = {"live_av_verified": False, "human_full_watch_count": 0,
                "allowed_media_root": "runs/visual_qc", "ffprobe_available": bool(shutil.which("ffprobe"))}
        try:
            profile = load_profile(self.root, environ=self.environ)
        except ConfigurationError as error:
            return {**base, "status": "CONFIGURATION_ERROR", "error": str(error)}
        ready = bool(self.environ.get(profile.api_key_env, "").strip())
        return {**base, "status": "CONFIGURED_NOT_LIVE_VERIFIED" if ready else "API_KEY_MISSING",
                "profile": profile.name, "provider": profile.provider, "model": profile.model,
                "api_key_env": profile.api_key_env, "key_available": ready}

    def inspect_clip(self, media_path: str) -> dict:
        return inspect_clip(self.root, media_path).public(self.root)

    def prepare_visual_clip(self, media_path: str, expected_sha256: str, fps: float = 4.0) -> dict:
        clip = inspect_clip(self.root, media_path)
        if expected_sha256 != clip.sha256:
            raise MediaError("Source hash differs from the inspected media hash")
        validate_frame_budget(fps, clip.duration)
        directory = self._new_run()
        frames = extract_frames(clip, directory, fps)
        manifest = {
            "status": "LOCAL_FRAMES_PREPARED", "uploaded": False,
            "source": clip.public(self.root), "requested_fps": fps,
            "artifact_dir": str(directory.relative_to(self.root)),
            "frames": [{"path": str(f.path.relative_to(self.root)),
                        "time_seconds": f.time, "sha256": f.sha256} for f in frames],
            "input_kind": "TIMESTAMPED_STILLS_NO_AUDIO", "audio_included": False,
            "human_full_watch_count": 0, "may_issue_verdict": False,
            "limitations": ["Still frames are not continuous AV input", "L2 remains incomplete"],
        }
        with (directory / "frames-manifest.json").open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
        return manifest

    def review_clip(self, media_path: str, allow_upload: bool = False,
                    expected_sha256: str = "", fps: float = 8.0) -> dict:
        if allow_upload is not True:
            return {"status": "UPLOAD_CONFIRMATION_REQUIRED", "uploaded": False}
        profile = load_profile(self.root, environ=self.environ)
        if profile.provider != "google-gemini":
            raise ConfigurationError("av_review_clip requires google-gemini; use grok_screen_clip for xai-grok")
        key = profile.get_key(self.environ)
        clip = inspect_clip(self.root, media_path)
        validate_sampling(fps, clip.duration)
        if expected_sha256 != clip.sha256:
            raise MediaError("Source hash differs from the inspected/authorized media hash")
        video = clip.path.read_bytes()
        if len(video) > MAX_BYTES or hashlib.sha256(video).hexdigest() != clip.sha256:
            raise MediaError("Source hash or size changed before upload")
        directory = self._new_run()
        manifest = {"media": clip.public(self.root), "profile": profile.name, "provider": profile.provider,
                    "model": profile.model, "requested_fps": fps,
                    "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest()}
        self._save(directory / "request-manifest.json", manifest, key)
        (directory / "review-prompt.txt").write_text(PROMPT, encoding="utf-8")
        started = time.monotonic()
        try:
            raw = self.transport(profile, key, build_request(video, fps))
        except ProviderError as error:
            report = self._report(directory, clip, fps, "REQUEST_FAILED_OUTCOME_UNKNOWN")
            report["error"] = str(error).replace(key, "[REDACTED]")
        else:
            self._save(directory / "provider-response.json", raw, key)
            body, issues = extract_assessment(raw, clip.duration)
            report = self._report(directory, clip, fps,
                                  "MODEL_RESPONSE_INVALID" if issues else "MODEL_RESPONSE_RECORDED")
            report.update({"assessment": body, "issues": issues})
            report["response_model_version"] = raw.get("modelVersion", "UNREPORTED")
        report["request_elapsed_seconds"] = round(time.monotonic() - started, 3)
        report["attempts"] = 1
        self._save(directory / "report.json", report, key)
        return json.loads(json.dumps(report, ensure_ascii=False).replace(key, "[REDACTED]"))

    def _new_run(self) -> Path:
        root = self.root / "runs/visual_qc/av_mcp"
        if not root.resolve().is_relative_to(self.root / "runs/visual_qc"):
            raise MediaError("Output path escaped the allowed output root")
        name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12]
        directory = root / name
        directory.mkdir(parents=True, exist_ok=False)
        return directory

    def _report(self, directory: Path, clip, fps: float, status: str) -> dict:
        return {
            "schema": "unit_av_mcp_report_v1", "status": status,
            "artifact_dir": str(directory.relative_to(self.root)), "source_sha256": clip.sha256,
            "requested_fps": fps, "effective_fps": "UNVERIFIED",
            "reviewer_kind": "model", "human_full_watch_count": 0, "may_issue_verdict": False,
        }

    @staticmethod
    def _save(path: Path, data: dict, key: str) -> None:
        text = json.dumps(data, indent=2, ensure_ascii=False).replace(key, "[REDACTED]")
        with path.open("x", encoding="utf-8") as handle:
            handle.write(text + "\n")
