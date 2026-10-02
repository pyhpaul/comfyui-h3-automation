import sys
import shutil
import subprocess
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
from h3_test2_ep01_finalize import concat_mp4, media_summary, probe, video_source


def test_video_source_requires_the_verified_unit_downloads_directory() -> None:
    source = "/content/h3-test2-ep01/U01/run/downloads/job/output.mp4"
    assert video_source("U01", {"video": {"path": source}}) == "downloads/job/output.mp4"
    for rejected in (
        "/content/h3-test2-ep01/U02/run/downloads/output.mp4",
        "/content/h3-test2-ep01/U01/run/../other/output.mp4",
        "/content/h3-test2-ep01/U01/run/downloads/output.safetensors",
    ):
        with pytest.raises(RuntimeError, match="unexpected video path"):
            video_source("U01", {"video": {"path": rejected}})


def test_media_summary_requires_unchanged_final_stream_profile() -> None:
    media = {
        "format": {"duration": "126.666"},
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 768,
             "height": 1376, "r_frame_rate": "24/1", "nb_frames": "3040",
             "duration": "126.666", "start_time": "0.0"},
            {"codec_type": "audio", "codec_name": "aac",
             "duration": "126.650", "start_time": "0.0"},
        ],
    }
    assert media_summary(media)["video_frames"] == 3040
    media["streams"][0]["width"] = 720
    with pytest.raises(RuntimeError, match="unexpected codec"):
        media_summary(media)


def test_concat_stream_copy_keeps_both_video_and_audio(tmp_path: Path) -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg and ffprobe are required for media smoke")
    for name, color, frequency in (("U01.mp4", "red", "400"),
                                   ("U02.mp4", "blue", "800")):
        subprocess.run([
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-n",
            "-f", "lavfi", "-i", f"color=c={color}:s=96x96:r=24:d=0.5",
            "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration=0.5",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-shortest", str(tmp_path / name),
        ], check=True, timeout=30)
    output = tmp_path / "final.mp4"
    concat_mp4(tmp_path, ["U01.mp4", "U02.mp4"], output)
    streams = probe(output)["streams"]
    video = next(item for item in streams if item["codec_type"] == "video")
    audio = next(item for item in streams if item["codec_type"] == "audio")
    assert video["codec_name"] == "h264"
    assert audio["codec_name"] == "aac"
    assert video["nb_frames"] == "24"
