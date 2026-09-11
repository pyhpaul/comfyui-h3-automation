from __future__ import annotations
from pathlib import Path
from typing import Any
from comfy_orch.client import ComfyClient

def collect_outputs(
    client: ComfyClient,
    history_entry: dict[str, Any],
    dest_dir: Path,
    *,
    prefer_node_ids: list[str] | None = None,
) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    outputs = history_entry.get("outputs") or {}
    node_order = list(prefer_node_ids or []) + [n for n in outputs if n not in (prefer_node_ids or [])]
    seen: set[str] = set()
    for node in node_order:
        if node in seen or node not in outputs:
            continue
        seen.add(node)
        payload = outputs[node]
        for key in ("images", "gifs", "videos"):
            for item in payload.get(key) or []:
                filename = item["filename"]
                dest = dest_dir / filename
                client.download_view(
                    filename=filename,
                    dest=dest,
                    subfolder=item.get("subfolder") or "",
                    type_=item.get("type") or "output",
                )
                saved.append(dest)
    return saved
