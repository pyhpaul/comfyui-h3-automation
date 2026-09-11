from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from comfy_orch.errors import ValidationError


@dataclass
class JobSpec:
    template: str
    fields: dict[str, Any]
    job_dir: Path

    def resolve_path(self, field_name: str) -> Path:
        rel = self.fields[field_name]
        return (self.job_dir / rel).resolve()


def _load_yaml(path: Path, label: str) -> Any:
    if not path.is_file():
        raise ValidationError(f"missing {label}: {path}")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValidationError(f"invalid YAML in {label}: {path}") from exc


def load_and_validate_job(job_dir: Path, schema_path: Path) -> JobSpec:
    job_dir = job_dir.resolve()
    job_file = job_dir / "job.yaml"
    if not job_file.is_file():
        raise ValidationError(f"missing job.yaml in {job_dir}")

    raw = _load_yaml(job_file, "job.yaml")
    template = raw.get("template")
    fields = raw.get("fields") or {}
    if not template:
        raise ValidationError("job.yaml missing template")

    schema = _load_yaml(schema_path, "schema")
    for key in schema.get("required_fields") or []:
        if key not in fields or fields[key] in (None, ""):
            raise ValidationError(f"missing required field: {key}")
    for key in schema.get("required_files") or []:
        if key not in fields:
            raise ValidationError(f"missing required file field: {key}")
        path = (job_dir / str(fields[key])).resolve()
        if not path.is_relative_to(job_dir):
            raise ValidationError(f"path for {key} escapes job_dir: {fields[key]}")
        if not path.is_file():
            raise ValidationError(f"missing file for {key}: {fields[key]}")

    for key in schema.get("optional_files") or []:
        if key not in fields or fields[key] in (None, ""):
            continue
        path = (job_dir / str(fields[key])).resolve()
        if not path.is_relative_to(job_dir):
            raise ValidationError(f"path for {key} escapes job_dir: {fields[key]}")
        if not path.is_file():
            raise ValidationError(f"missing file for {key}: {fields[key]}")

    return JobSpec(template=str(template), fields=dict(fields), job_dir=job_dir)
