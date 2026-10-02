"""Container labels must not masquerade as generated media changes."""

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
from h3_a100_media import decoded_stream_sha256, media_timeline, media_timeline_sha256


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg unavailable")
def test_decoded_hash_ignores_container_metadata(tmp_path):
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    subprocess.run([
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=red:s=64x64:r=24:d=1",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-shortest", "-metadata", "title=first", str(first),
    ], check=True, timeout=30)
    subprocess.run([
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(first), "-map", "0", "-c", "copy",
        "-metadata", "title=second", str(second),
    ], check=True, timeout=30)
    assert hashlib.sha256(first.read_bytes()).digest() != hashlib.sha256(second.read_bytes()).digest()
    for kind in ("video", "audio"):
        assert decoded_stream_sha256(first, kind) == decoded_stream_sha256(second, kind)
        assert media_timeline(first, kind) == media_timeline(second, kind)
        assert media_timeline_sha256(first, kind) == media_timeline_sha256(second, kind)


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
                    reason="ffmpeg/ffprobe unavailable")
def test_timeline_detects_timestamp_shift_without_pixel_change(tmp_path):
    first = tmp_path / "first.mp4"
    shifted = tmp_path / "shifted.mp4"
    subprocess.run([
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=red:s=64x64:r=24:d=1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(first),
    ], check=True, timeout=30)
    subprocess.run([
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-itsoffset", "0.5", "-i", str(first), "-c", "copy", str(shifted),
    ], check=True, timeout=30)
    assert decoded_stream_sha256(first, "video") == decoded_stream_sha256(shifted, "video")
    assert media_timeline(first, "video") != media_timeline(shifted, "video")
    assert media_timeline_sha256(first, "video") != media_timeline_sha256(shifted, "video")


def test_decoded_hash_rejects_unsupported_stream(tmp_path):
    with pytest.raises(ValueError, match="unsupported"):
        decoded_stream_sha256(tmp_path / "missing.mp4", "subtitle")
    with pytest.raises(ValueError, match="unsupported"):
        media_timeline(tmp_path / "missing.mp4", "subtitle")
