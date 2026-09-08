from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

import yaml

from comfy_orch.artifacts import collect_outputs
from comfy_orch.binder import apply_bindings, list_media_fields
from comfy_orch.client import ComfyClient
from comfy_orch.errors import ComfyOrchError, ValidationError
from comfy_orch.manifest import load_and_validate_job
from comfy_orch.status import JobStatus, write_status

_lock = threading.Lock()


def submit_job(job_dir: Path, *, base_url: str, root: Path) -> str:
    with _lock:
        job_id = uuid.uuid4().hex[:12]
        status_path = root / "runs" / job_id / "status.json"
        write_status(status_path, JobStatus(job_id=job_id, state="validating"))

        def _write_failed(message: str) -> None:
            write_status(
                status_path,
                JobStatus(job_id=job_id, state="failed", message=message),
            )

        try:
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

            client = ComfyClient(base_url)
            try:
                client.system_stats()

                bindings_yaml = (template_dir / "bindings.yaml").read_text(encoding="utf-8")
                values = dict(job.fields)
                for field in list_media_fields(bindings_yaml):
                    remote_name = client.upload_image(job.resolve_path(field))
                    values[field] = remote_name

                workflow = json.loads(
                    (template_dir / "workflow_api.json").read_text(encoding="utf-8")
                )
                bound = apply_bindings(
                    workflow,
                    bindings_yaml=bindings_yaml,
                    values=values,
                )
                prompt_id = client.queue_prompt(bound)
                write_status(
                    status_path,
                    JobStatus(job_id=job_id, state="running", prompt_id=prompt_id),
                )

                history = client.wait_until_done(prompt_id, poll_interval=0.01)
                out_dir = root / "outputs" / job_id
                saved = collect_outputs(client, history, out_dir)
                write_status(
                    status_path,
                    JobStatus(
                        job_id=job_id,
                        state="done",
                        prompt_id=prompt_id,
                        outputs=[str(p) for p in saved],
                    ),
                )
            finally:
                client.close()
        except ValidationError as exc:
            _write_failed(str(exc))
            raise
        except ComfyOrchError as exc:
            _write_failed(str(exc))
            raise

        return job_id
