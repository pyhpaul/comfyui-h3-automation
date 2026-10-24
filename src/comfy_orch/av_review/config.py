from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit


class ConfigurationError(ValueError):
    """Non-secret configuration error safe to return to an MCP caller."""


@dataclass(frozen=True)
class Profile:
    name: str
    provider: str
    base_url: str
    api_key_env: str
    model: str

    def get_key(self, environ: Mapping[str, str]) -> str:
        key = environ.get(self.api_key_env, "").strip()
        if not key:
            raise ConfigurationError(f"Missing API key in environment variable {self.api_key_env}")
        return key


def _validate_profile(profile: Profile) -> None:
    url = urlsplit(profile.base_url)
    endpoints = {"google-gemini": ("generativelanguage.googleapis.com", "/v1beta", "gemini-"),
                 "xai-grok": ("api.x.ai", "/v1", "grok-")}
    if profile.provider not in endpoints:
        raise ConfigurationError("Unsupported AV review provider")
    host, path, prefix = endpoints[profile.provider]
    if (url.scheme != "https" or url.netloc != host
            or url.path != path or url.query or url.fragment):
        raise ConfigurationError("Profile endpoint is not the approved provider endpoint")
    if not re.fullmatch(re.escape(prefix) + r"[A-Za-z0-9._-]+", profile.model):
        raise ConfigurationError("Invalid provider model identifier")
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*API_KEY", profile.api_key_env):
        raise ConfigurationError("api_key_env must name an API_KEY environment variable")


def load_profile(
    project_root: Path,
    name: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> Profile:
    env = os.environ if environ is None else environ
    selected = name or env.get("H3_AV_REVIEW_PROFILE") or env.get("LLM_PROFILE") or "h3-av-review"
    path = Path(env.get("H3_AV_REVIEW_PROFILES") or env.get("LLM_PROFILES_PATH")
                or project_root / "config/av_review_profiles.toml").expanduser()
    if not path.is_absolute():
        path = project_root / path
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        raise ConfigurationError("Cannot read a valid AV review profile file") from None
    profiles = data.get("profiles", {})
    raw = profiles.get(selected) if isinstance(profiles, dict) else None
    fields = ("provider", "base_url", "api_key_env", "model")
    if not isinstance(raw, dict) or any(not isinstance(raw.get(f), str) for f in fields):
        raise ConfigurationError(f"Missing or incomplete AV review profile: {selected}")
    profile = Profile(selected, **{f: raw[f].rstrip("/") if f == "base_url" else raw[f] for f in fields})
    _validate_profile(profile)
    return profile
