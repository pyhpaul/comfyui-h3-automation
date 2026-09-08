from __future__ import annotations

import copy
from typing import Any

import yaml

from comfy_orch.errors import ValidationError


def apply_bindings(
    workflow: dict[str, Any],
    *,
    bindings_yaml: str,
    values: dict[str, Any],
) -> dict[str, Any]:
    cfg = yaml.safe_load(bindings_yaml) or {}
    out = copy.deepcopy(workflow)
    for item in cfg.get("bindings") or []:
        field = item["field"]
        if field not in values:
            continue
        node_id = _resolve_node_id(out, item)
        input_name = item["input"]
        out[node_id]["inputs"][input_name] = values[field]
    return out


def list_media_fields(bindings_yaml: str) -> list[str]:
    cfg = yaml.safe_load(bindings_yaml) or {}
    return [i["field"] for i in (cfg.get("bindings") or []) if i.get("media")]


def _resolve_node_id(workflow: dict[str, Any], item: dict[str, Any]) -> str:
    if title := item.get("node_title"):
        for nid, node in workflow.items():
            meta = node.get("_meta") or {}
            if meta.get("title") == title:
                return str(nid)
        raise ValidationError(f"node title not found: {title}")
    if nid := item.get("node_id"):
        if str(nid) not in workflow:
            raise ValidationError(f"node id not found: {nid}")
        return str(nid)
    raise ValidationError("binding needs node_title or node_id")
