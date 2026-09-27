import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
from h3_test2_ep01_media import validate_latent_shapes, validate_video_metadata


def tensors() -> list[dict]:
    return [
        {"name": "audio", "shape": [1, 32, 2, 603], "dtype": "torch.float32", "finite": True},
        {"name": "video", "shape": [1, 24, 107, 86, 48], "dtype": "torch.float32", "finite": True},
    ]


def media() -> dict:
    return {
        "format": {"duration": "15.083333"},
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 768,
             "height": 1376, "r_frame_rate": "24/1", "nb_frames": "362",
             "duration": "15.083333", "start_time": "0.000000"},
            {"codec_type": "audio", "codec_name": "aac",
             "duration": "15.072000", "start_time": "0.000000"},
        ],
    }


def test_latent_accepts_plausible_first_unit_and_frozen_temporal() -> None:
    validate_latent_shapes(tensors())
    validate_latent_shapes(tensors(), expected_temporal=107)


@pytest.mark.parametrize("field,value", [("finite", False), ("dtype", "torch.float16")])
def test_latent_rejects_corrupt_tensor(field: str, value: object) -> None:
    changed = tensors()
    changed[1][field] = value
    with pytest.raises(RuntimeError, match="latent shape"):
        validate_latent_shapes(changed)


def test_latent_rejects_changed_temporal_after_u01() -> None:
    with pytest.raises(RuntimeError, match="latent shape"):
        validate_latent_shapes(tensors(), expected_temporal=106)


def test_video_accepts_expected_aac_h264_shape() -> None:
    validate_video_metadata(media(), "U01")


def test_chained_unit_has_22_frame_trim() -> None:
    chained = media()
    chained["format"]["duration"] = "14.166667"
    chained["streams"][0]["nb_frames"] = "340"
    chained["streams"][0]["duration"] = "14.166667"
    chained["streams"][1]["duration"] = "14.155000"
    validate_video_metadata(chained, "U02")


def test_video_rejects_short_or_audio_skew() -> None:
    short = copy.deepcopy(media())
    short["format"]["duration"] = "14.000000"
    with pytest.raises(RuntimeError, match="metadata"):
        validate_video_metadata(short, "U01")
    skew = copy.deepcopy(media())
    skew["streams"][1]["duration"] = "14.000000"
    with pytest.raises(RuntimeError, match="metadata"):
        validate_video_metadata(skew, "U01")
