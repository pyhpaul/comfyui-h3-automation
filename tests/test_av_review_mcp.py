"""SDK integration tests; use the isolated MCP test environment described in the runbook."""

import asyncio
import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("mcp")
from mcp import Client


ROOT = Path(__file__).resolve().parents[1]


def load_server():
    spec = importlib.util.spec_from_file_location("unit_av_review_mcp", ROOT / "scripts/ops/unit_av_review_mcp.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mcp_status_and_upload_denial_are_real_tool_calls(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("H3_AV_REVIEW_PROFILES", str(ROOT / "config/av_review_profiles.toml"))
    monkeypatch.setenv("H3_AV_REVIEW_PROFILE", "h3-av-review")
    server = load_server().create_server(ROOT)

    async def exercise():
        async with Client(server) as client:
            status = await client.call_tool("av_review_status", {})
            denied = await client.call_tool("av_review_clip", {
                "media_path": "not-read.mp4", "expected_sha256": "", "allow_upload": False,
            })
        return status.structured_content, denied.structured_content

    status, denied = asyncio.run(exercise())
    assert status["status"] == "API_KEY_MISSING"
    assert denied["status"] == "UPLOAD_CONFIRMATION_REQUIRED"
    assert denied["uploaded"] is False
