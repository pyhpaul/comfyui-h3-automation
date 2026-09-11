from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import yaml

from comfy_orch.export_bound import build_bound_workflow, export_bound_workflow_for_job


def test_build_bound_workflow_uploads_media_and_applies_text(tmp_path: Path):
    root = tmp_path
    template_dir = root / "templates" / "yz_h3_ep_unit"
    template_dir.mkdir(parents=True)
    (template_dir / "workflow_api.json").write_text(
        json.dumps(
            {
                "51": {
                    "inputs": {"image": ""},
                    "class_type": "LoadImage",
                    "_meta": {"title": "YZ控制图"},
                },
                "263": {
                    "inputs": {"text": ""},
                    "class_type": "Text Multiline",
                    "_meta": {"title": "YZ提示词"},
                },
                "259": {
                    "inputs": {"value": 1},
                    "class_type": "PrimitiveFloat",
                    "_meta": {"title": "视频时长（秒）"},
                },
            }
        ),
        encoding="utf-8",
    )
    (template_dir / "bindings.yaml").write_text(
        "bindings:\n"
        "  - field: ref_image_0\n"
        "    node_title: YZ控制图\n"
        "    input: image\n"
        "    media: true\n"
        "  - field: prompt\n"
        "    node_title: YZ提示词\n"
        "    input: text\n"
        "  - field: duration_seconds\n"
        "    node_title: 视频时长（秒）\n"
        "    input: value\n",
        encoding="utf-8",
    )
    (template_dir / "manifest.schema.yaml").write_text(
        "required_fields: [prompt, duration_seconds]\n"
        "required_files: [ref_image_0]\n",
        encoding="utf-8",
    )

    job_dir = tmp_path / "job"
    (job_dir / "assets").mkdir(parents=True)
    img = job_dir / "assets" / "control.png"
    img.write_bytes(b"png")
    (job_dir / "job.yaml").write_text(
        yaml.safe_dump(
            {
                "template": "yz_h3_ep_unit",
                "fields": {
                    "ref_image_0": "assets/control.png",
                    "prompt": "hello prompt",
                    "duration_seconds": 10,
                },
            }
        ),
        encoding="utf-8",
    )

    client = MagicMock()
    client.upload_image.return_value = "remote-control.png"

    bound = build_bound_workflow(job_dir, root=root, client=client)
    assert bound["51"]["inputs"]["image"] == "remote-control.png"
    assert bound["263"]["inputs"]["text"] == "hello prompt"
    assert bound["259"]["inputs"]["value"] == 10
    client.upload_image.assert_called_once()


def test_export_writes_json(tmp_path: Path):
    root = tmp_path
    template_dir = root / "templates" / "demo"
    template_dir.mkdir(parents=True)
    (template_dir / "workflow_api.json").write_text(
        json.dumps(
            {
                "1": {
                    "inputs": {"text": ""},
                    "class_type": "Text",
                    "_meta": {"title": "正向提示词"},
                }
            }
        ),
        encoding="utf-8",
    )
    (template_dir / "bindings.yaml").write_text(
        "bindings:\n  - field: prompt\n    node_title: 正向提示词\n    input: text\n",
        encoding="utf-8",
    )
    (template_dir / "manifest.schema.yaml").write_text(
        "required_fields: [prompt]\nrequired_files: []\n",
        encoding="utf-8",
    )
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "job.yaml").write_text(
        "template: demo\nfields:\n  prompt: hi\n",
        encoding="utf-8",
    )
    client = MagicMock()
    out = tmp_path / "out.json"
    path, ui_path = export_bound_workflow_for_job(
        job_dir, root=root, client=client, out_path=out
    )
    assert path == out
    assert ui_path is None
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["1"]["inputs"]["text"] == "hi"
