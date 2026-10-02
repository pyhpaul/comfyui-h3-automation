from __future__ import annotations

import json
from pathlib import Path

from comfy_orch.binder import apply_bindings
from comfy_orch.ui_bind import prune_unused_api_ref_images


TEMPLATE = Path(__file__).resolve().parents[1] / "templates/yz_h3_ep_unit"


def bound_graph(ref_count: int) -> dict:
    workflow = json.loads((TEMPLATE / "workflow_api.json").read_text(encoding="utf-8"))
    bindings = (TEMPLATE / "bindings.yaml").read_text(encoding="utf-8")
    values = {
        **{f"ref_image_{i}": f"uploaded-{i}.png" for i in range(ref_count)},
        "prompt": "test",
        "duration_seconds": 15.083,
        "aspect_ratio": "9:16 (Portrait Widescreen)",
        "megapixels": 1.0,
        "filename_prefix": "nine-refs-test",
    }
    return prune_unused_api_ref_images(
        apply_bindings(workflow, bindings_yaml=bindings, values=values), values=values
    )


def test_all_nine_reference_images_reach_h3():
    graph = bound_graph(9)
    inputs = graph["265"]["inputs"]

    assert sum(name.startswith("ref_images.") for name in inputs) == 9
    for index, node in ((6, "407"), (7, "408"), (8, "409")):
        assert graph[node]["inputs"]["image"] == f"uploaded-{index}.png"
        assert inputs[f"ref_images.ref_image_{index}"] == [node, 0]


def test_unused_extra_reference_nodes_are_pruned():
    graph = bound_graph(6)

    assert all(f"ref_images.ref_image_{i}" not in graph["265"]["inputs"] for i in range(6, 9))
    assert all(node not in graph for node in ("407", "408", "409"))
