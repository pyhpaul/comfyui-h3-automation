from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from comfy_orch.binder import apply_bindings, list_media_fields
from comfy_orch.client import ComfyClient
from comfy_orch.errors import ValidationError
from comfy_orch.manifest import JobSpec, load_and_validate_job
from comfy_orch.ui_bind import YZ_UI_AUDIO_NODES, export_bound_ui_workflow, prune_unused_api_ref_images

SILENT_AUDIO_REL = Path("assets") / "silent_placeholder.wav"


def prepare_job_values(
    job_dir: Path,
    *,
    root: Path,
    client: ComfyClient,
) -> tuple[JobSpec, dict[str, Any], Path]:
    """Validate job, upload media fields, return values ready for binding."""
    job_file = job_dir.resolve() / "job.yaml"
    if not job_file.is_file():
        raise ValidationError(f"missing job.yaml in {job_dir}")
    raw = yaml.safe_load(job_file.read_text(encoding="utf-8")) or {}
    template = raw.get("template")
    if not template:
        raise ValidationError("job.yaml missing template")

    schema_path = root / "templates" / template / "manifest.schema.yaml"
    job = load_and_validate_job(job_dir, schema_path=schema_path)
    template_dir = root / "templates" / job.template
    bindings_path = template_dir / "bindings.yaml"
    if not bindings_path.is_file():
        raise ValidationError(f"missing bindings.yaml for template {job.template}")

    bindings_yaml = bindings_path.read_text(encoding="utf-8")
    values = dict(job.fields)
    for field in list_media_fields(bindings_yaml):
        if field not in job.fields:
            continue
        values[field] = client.upload_image(job.resolve_path(field))

    # EP packs usually have empty audio_uploads; YZ UI still requires 3 LoadAudio files.
    if not any(k in values for k in YZ_UI_AUDIO_NODES):
        silent = template_dir / SILENT_AUDIO_REL
        if silent.is_file():
            remote = client.upload_image(silent)
            for key in YZ_UI_AUDIO_NODES:
                values[key] = remote

    return job, values, template_dir


def build_bound_workflow(
    job_dir: Path,
    *,
    root: Path,
    client: ComfyClient,
) -> dict[str, Any]:
    job, values, template_dir = prepare_job_values(job_dir, root=root, client=client)
    workflow_path = template_dir / "workflow_api.json"
    if not workflow_path.is_file():
        raise ValidationError(f"missing workflow_api.json for template {job.template}")
    bindings_yaml = (template_dir / "bindings.yaml").read_text(encoding="utf-8")
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    bound = apply_bindings(workflow, bindings_yaml=bindings_yaml, values=values)
    return prune_unused_api_ref_images(bound, values=values)


def export_bound_workflow_for_job(
    job_dir: Path,
    *,
    root: Path,
    client: ComfyClient,
    out_path: Path,
    out_ui_path: Path | None = None,
) -> tuple[Path, Path | None]:
    job, values, template_dir = prepare_job_values(job_dir, root=root, client=client)
    workflow_path = template_dir / "workflow_api.json"
    if not workflow_path.is_file():
        raise ValidationError(f"missing workflow_api.json for template {job.template}")
    bindings_yaml = (template_dir / "bindings.yaml").read_text(encoding="utf-8")
    bound_api = apply_bindings(
        json.loads(workflow_path.read_text(encoding="utf-8")),
        bindings_yaml=bindings_yaml,
        values=values,
    )
    bound_api = prune_unused_api_ref_images(bound_api, values=values)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(bound_api, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    ui_written: Path | None = None
    ui_src = template_dir / "workflow_ui.json"
    if out_ui_path is not None:
        if not ui_src.is_file():
            raise ValidationError(f"missing workflow_ui.json for template {job.template}")
        ui_written = export_bound_ui_workflow(
            ui_workflow_path=ui_src,
            values=values,
            out_path=out_ui_path,
        )
    return out_path, ui_written
