# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp==2.3.0"]
# ///
"""Project-scoped stdio AV review tools, with isolated SDK dependencies via uv."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from comfy_orch.av_review.service import ReviewService


def create_server(root: Path = ROOT):
    server = MCPServer("h3-av-review")
    service = ReviewService(root)

    @server.tool(structured_output=True, annotations=ToolAnnotations(
        readOnlyHint=True, openWorldHint=False, idempotentHint=True))
    def av_review_status() -> dict[str, object]:
        """Check profile/key readiness locally, without uploading media or making API calls."""
        return service.status()

    @server.tool(structured_output=True, annotations=ToolAnnotations(
        readOnlyHint=True, openWorldHint=False, idempotentHint=True))
    def av_inspect_clip(media_path: str) -> dict[str, object]:
        """Inspect/hash a local MP4 under runs/visual_qc; no upload. Return hash needed to authorize review."""
        return service.inspect_clip(media_path)

    @server.tool(structured_output=True, annotations=ToolAnnotations(
        readOnlyHint=False, openWorldHint=False, destructiveHint=False, idempotentHint=False))
    def av_prepare_visual_clip(media_path: str, expected_sha256: str,
                               fps: float = 4.0) -> dict[str, object]:
        """Locally extract hash-bound timestamped JPEGs, without API keys or network calls.

        Caller can read these images using its own vision model (including Cursor Grok).
        Max 64 frames, fps 1-8, source <=12 MiB/30s. No audio is included. Not full L2.
        Creates a new evidence directory; never overwrites source media or reviews.
        """
        return service.prepare_visual_clip(media_path, expected_sha256, fps)

    @server.tool(structured_output=True, annotations=ToolAnnotations(
        readOnlyHint=False, openWorldHint=True, destructiveHint=False, idempotentHint=False))
    def av_review_clip(media_path: str, expected_sha256: str, allow_upload: bool = False,
                       fps: float = 8.0) -> dict[str, object]:
        """Send one authorized clip to the configured native Gemini API (may incur charges).

        Requires explicit upload consent and exact previously inspected hash. Max 12 MiB,
        30 seconds, 240 requested frames; no retries. Saves local evidence, never a human
        verdict or registry approval. Requested fps does not prove effective sampling.
        """
        return service.review_clip(media_path, allow_upload, expected_sha256, fps)

    return server


if __name__ == "__main__":
    create_server().run(transport="stdio")
