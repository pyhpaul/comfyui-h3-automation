from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from comfy_orch.binder import apply_bindings
from comfy_orch.gpu_adapt import apply_gpu_profile, resolve_gpu_profile
from comfy_orch.render_profile import RenderProfile, apply_render_profile
from comfy_orch.ui_bind import prune_unused_api_ref_images

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
from h3_test2_ep23_contract import parent_unit, validate_graph


TEMPLATE = Path(__file__).resolve().parents[1] / "templates/yz_h3_ep_unit"


def graph(episode: str, unit: str, refs: int) -> tuple[dict, str | None]:
    workflow = json.loads((TEMPLATE / "workflow_api.json").read_text(encoding="utf-8"))
    bindings = (TEMPLATE / "bindings.yaml").read_text(encoding="utf-8")
    values = {
        **{f"ref_image_{number}": f"upload-{number}.png" for number in range(refs)},
        "prompt": "test", "duration_seconds": 15.083,
        "aspect_ratio": "9:16 (Portrait Widescreen)", "megapixels": 1.0,
        "filename_prefix": f"{episode}-{unit}-test2",
    }
    parent = parent_unit(episode, unit)
    parent_path = f"h3_context/{episode.lower()}_{parent.lower()}_00001.safetensors" if parent else None
    bound = prune_unused_api_ref_images(
        apply_bindings(workflow, bindings_yaml=bindings, values=values), values=values)
    profile = RenderProfile(
        continuity="motion_latent", save_clip_index=int(unit[1:]),
        load_clip_index=int(parent[1:]) if parent else 0,
        motion_latent_path=parent_path,
        latent_filename_prefix=f"h3_context/{episode.lower()}_{unit.lower()}",
    )
    return apply_gpu_profile(
        apply_render_profile(bound, profile, filename_prefix=values["filename_prefix"]),
        resolve_gpu_profile("rtx5090"),
    ), parent_path


@pytest.mark.parametrize(
    ("episode", "unit", "refs"),
    [("EP02", "U01", 9), ("EP02", "U02", 4), ("EP02", "U03", 4),
     ("EP02", "U04", 3), ("EP02", "U06", 9), ("EP03", "U01", 9),
     ("EP03", "U07", 9)],
)
def test_accepted_topology_matches_one_pass_graph(episode: str, unit: str, refs: int) -> None:
    workflow, parent_path = graph(episode, unit, refs)
    validate_graph(workflow, episode, unit, parent_path, refs)


def test_cross_scene_independent_start_rejects_parent_latent() -> None:
    workflow, _ = graph("EP02", "U02", 4)
    with pytest.raises(RuntimeError, match="independent start"):
        validate_graph(workflow, "EP02", "U02", "h3_context/ep02_u01_00001.safetensors", 4)
