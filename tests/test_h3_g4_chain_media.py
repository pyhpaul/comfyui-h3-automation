import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
from h3_g4_chain_media import validate_latent_shapes, validate_video_metadata


def media(duration: float, frames: int) -> dict:
    return {"format": {"duration": str(duration)}, "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 768,
         "height": 1376, "r_frame_rate": "24/1", "nb_frames": str(frames),
         "duration": str(duration), "start_time": "0.0"},
        {"codec_type": "audio", "codec_name": "aac", "duration": str(duration - 0.014),
         "start_time": "0.0"},
    ]}


def test_duration_aware_video_accepts_u02_and_u04_lengths() -> None:
    validate_video_metadata(media(12.75, 306), 12)
    validate_video_metadata(media(13.75, 330), 13)


def test_duration_aware_video_rejects_short_or_wrong_codec() -> None:
    with pytest.raises(RuntimeError, match="unexpected G4 chain media"):
        validate_video_metadata(media(12.75, 306), 13)
    wrong = media(13.75, 330)
    wrong["streams"][1]["codec_name"] = "mp3"
    with pytest.raises(RuntimeError, match="unexpected G4 chain media"):
        validate_video_metadata(wrong, 13)


def test_latent_checks_shape_dtype_and_finiteness() -> None:
    tensors = [{"name": "audio", "shape": [1, 32, 2, 547],
                "dtype": "torch.float32", "finite": True},
               {"name": "video", "shape": [1, 24, 97, 86, 48],
                "dtype": "torch.float32", "finite": True}]
    validate_latent_shapes(tensors, 12)
    longer = copy.deepcopy(tensors)
    longer[0]["shape"][3] = 590
    longer[1]["shape"][2] = 105
    validate_latent_shapes(longer, 13)
    longer[1]["finite"] = False
    with pytest.raises(RuntimeError, match="AV latent shape"):
        validate_latent_shapes(longer, 13)
