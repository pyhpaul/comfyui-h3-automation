import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
from h3_test2_ep01_contract import PARENTS, UNITS, job_name, validate_graph, validate_job

from comfy_orch.gpu_adapt import GpuProfile, apply_gpu_profile
from comfy_orch.render_profile import RenderProfile, apply_render_profile


ROOT = Path(__file__).resolve().parents[1]


def graph(unit: str, parent: str | None) -> dict:
    base = json.loads((ROOT / "templates/yz_h3_ep_unit/workflow_api.json").read_text())
    base["259"]["inputs"]["value"] = 15.083
    number = int(unit[1:])
    profile = RenderProfile(
        continuity="motion_latent",
        second_pass=False,
        save_clip_index=number,
        load_clip_index=(number - 1 if parent else 0),
        motion_latent_path=parent,
        latent_filename_prefix=f"h3_context/ep01_u{number:02d}",
    )
    return apply_gpu_profile(apply_render_profile(base, profile), GpuProfile.by_id("rtx5090"))


@pytest.mark.parametrize("unit", UNITS)
def test_selected_unit_graph_uses_expected_parent_and_duration(unit: str) -> None:
    parent = f"h3_context/{PARENTS[unit].lower()}.safetensors" if PARENTS[unit] else None
    validate_graph(graph(unit, parent), unit, parent)


def test_u05_rejects_cross_scene_parent() -> None:
    parent = "h3_context/u04.safetensors"
    with pytest.raises(RuntimeError, match="independent start"):
        validate_graph(graph("U05", parent), "U05", parent)


@pytest.mark.parametrize("unit", ("U01", "U05", "U06"))
def test_graph_rejects_duration_change(unit: str) -> None:
    parent = "h3_context/u05.safetensors" if unit == "U06" else None
    changed = graph(unit, parent)
    changed["259"]["inputs"]["value"] = 15.0
    with pytest.raises(RuntimeError, match="graph changed"):
        validate_graph(changed, unit, parent)


def test_u05_job_must_be_independent_candidate() -> None:
    job = {
        "template": "yz_h3_ep_unit",
        "unit_id": "U05",
        "parent_unit_id": None,
        "start_mode": "independent",
        "fields": {
            "duration_seconds": 15.083,
            "aspect_ratio": "9:16 (Portrait Widescreen)",
            "megapixels": 1.0,
            "filename_prefix": "EP01-U05-test2-independent-candidate",
            "ref_image_0": "assets/id0-char-001-w01.png",
            "ref_image_1": "assets/id1-scene-002-s01.png",
        },
    }
    assert job_name("U05") == "EP01-测试2-v1-U05-independent-candidate"
    validate_job(job, "U05")
    changed = copy.deepcopy(job)
    changed["parent_unit_id"] = "U04"
    with pytest.raises(RuntimeError, match="job mismatch"):
        validate_job(changed, "U05")
