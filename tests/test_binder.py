import json
from pathlib import Path

import pytest

from comfy_orch.binder import apply_bindings, list_media_fields
from comfy_orch.errors import ValidationError

FIXTURES = Path(__file__).parent / "fixtures" / "templates" / "demo"


def test_apply_by_title():
    workflow = json.loads((FIXTURES / "workflow_api.json").read_text(encoding="utf-8"))
    bindings = (FIXTURES / "bindings.yaml").read_text(encoding="utf-8")
    out = apply_bindings(
        workflow,
        bindings_yaml=bindings,
        values={"prompt": "NEW", "first_frame": "uploaded.png"},
    )
    assert out["6"]["inputs"]["text"] == "NEW"
    assert out["10"]["inputs"]["image"] == "uploaded.png"


def test_apply_by_node_id():
    workflow = json.loads((FIXTURES / "workflow_api.json").read_text(encoding="utf-8"))
    bindings = """
bindings:
  - field: prompt
    node_id: "6"
    input: text
"""
    out = apply_bindings(
        workflow,
        bindings_yaml=bindings,
        values={"prompt": "BY_ID"},
    )
    assert out["6"]["inputs"]["text"] == "BY_ID"


def test_list_media_fields():
    bindings = (FIXTURES / "bindings.yaml").read_text(encoding="utf-8")
    assert list_media_fields(bindings) == ["first_frame"]


def test_missing_node_title_raises():
    workflow = json.loads((FIXTURES / "workflow_api.json").read_text(encoding="utf-8"))
    bindings = """
bindings:
  - field: prompt
    node_title: missing
    input: text
"""
    with pytest.raises(ValidationError, match="node title not found"):
        apply_bindings(workflow, bindings_yaml=bindings, values={"prompt": "x"})
