"""Episode-post H.264 encoder selection (NVENC default)."""
from __future__ import annotations

from ep_pilot_media import burnin_video_encode_args, video_encode_args


def test_burnin_defaults_to_nvenc(monkeypatch):
    monkeypatch.delenv("H3_EP_VIDEO_ENCODER", raising=False)
    args = burnin_video_encode_args()
    assert args[:2] == ["-c:v", "h264_nvenc"]
    assert args[args.index("-cq") + 1] == "19"


def test_intermediate_and_concat_default_nvenc(monkeypatch):
    monkeypatch.delenv("H3_EP_VIDEO_ENCODER", raising=False)
    mid = video_encode_args(role="intermediate")
    cat = video_encode_args(role="concat")
    assert mid[:2] == ["-c:v", "h264_nvenc"]
    assert cat[:2] == ["-c:v", "h264_nvenc"]
    assert mid[mid.index("-cq") + 1] == "17"


def test_libx264_override_roles(monkeypatch):
    monkeypatch.setenv("H3_EP_VIDEO_ENCODER", "libx264")
    assert video_encode_args(role="burnin")[:4] == [
        "-c:v", "libx264", "-preset", "slow",
    ]
    assert video_encode_args(role="intermediate")[:4] == [
        "-c:v", "libx264", "-preset", "fast",
    ]
