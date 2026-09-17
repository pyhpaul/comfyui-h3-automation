#!/usr/bin/env python3
"""EP02 zero-state route test v1: U01-A→F, motion_latent 一采, path-wire only."""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path, PurePosixPath

import yaml

from comfy_orch.artifacts import collect_outputs
from comfy_orch.binder import apply_bindings, list_media_fields
from comfy_orch.client import ComfyClient
from comfy_orch.manifest import load_and_validate_job
from comfy_orch.paths import project_root
from comfy_orch.prompt_wire import audit_pack_prompt_wiring, wire_pack_prompt
from comfy_orch.render_profile import (
    RenderProfile,
    apply_render_profile,
    extract_saved_latent_path,
    preferred_video_node_ids,
)
from comfy_orch.status import JobStatus, write_status
from comfy_orch.ui_bind import prune_unused_api_ref_images

JOB_GLOB = "EP02-H3-zero-state-v1-{unit}"
LATENT_PREFIX = "h3_context/ep02_zero_state_v1"
DL_ROOT = Path("/mnt/c/Users/lxy/Downloads/EP02-H3-zero-state-route-test-v1")
UNITS = ["U01A", "U01B", "U01C", "U01D", "U01E", "U01F"]


def wait(client: ComfyClient, prompt_id: str, timeout: float = 7200.0) -> dict:
    start = time.time()
    while True:
        hist = client._client.get(f"/history/{prompt_id}").json()
        entry = hist.get(prompt_id)
        if entry:
            st = (entry.get("status") or {}).get("status_str")
            msgs = (entry.get("status") or {}).get("messages") or []
            interrupted = any(
                isinstance(m, (list, tuple)) and m and m[0] == "execution_interrupted"
                for m in msgs
            )
            if interrupted or st == "error":
                raise RuntimeError(
                    f"failed status={st} interrupted={interrupted} msgs={msgs[-3:]}"
                )
            if st == "success" or (entry.get("status") or {}).get("completed") is True:
                return entry
        q = client._client.get("/queue").json()
        run_ids = [
            i[1]
            for i in (q.get("queue_running") or [])
            if isinstance(i, list) and len(i) > 1
        ]
        pen_ids = [
            i[1]
            for i in (q.get("queue_pending") or [])
            if isinstance(i, list) and len(i) > 1
        ]
        state = (
            "running"
            if prompt_id in run_ids
            else ("pending" if prompt_id in pen_ids else "not_in_queue")
        )
        print(f"  wait {prompt_id[:8]} queue={state} elapsed={time.time()-start:.0f}s", flush=True)
        if state == "not_in_queue" and time.time() - start > 180:
            raise RuntimeError("lost from queue without history")
        if time.time() - start > timeout:
            raise TimeoutError(prompt_id)
        time.sleep(10)


def main() -> int:
    root = project_root()
    base = os.environ.get("COMFY_BASE_URL", "http://192.168.5.122:8190").rstrip("/")
    DL_ROOT.mkdir(parents=True, exist_ok=True)
    batch_log = root / "runs" / "ep02_zero_state_v1_motion_latent.json"
    client = ComfyClient(base, timeout=180.0)
    results: list[dict] = []
    parent_latent: str | None = None
    try:
        print(
            "doctor",
            (client.system_stats().get("devices") or [{}])[0].get("name"),
            "continuity=motion_latent second_pass=False pack=zero-state-v1",
            f"units={UNITS}",
            flush=True,
        )
        for i, unit in enumerate(UNITS):
            save_idx = i + 1
            load_idx = None if i == 0 else i
            job_dir = root / "jobs/ep_units" / JOB_GLOB.format(unit=unit)
            raw = yaml.safe_load((job_dir / "job.yaml").read_text(encoding="utf-8"))
            source = (job_dir / "assets" / "prompt_source.txt").read_text(encoding="utf-8")
            raw["fields"].pop("ref_video_0", None)
            ref_fields = {
                k: v for k, v in raw["fields"].items() if k.startswith("ref_image_")
            }
            wired = wire_pack_prompt(source, ref_fields)
            violations = audit_pack_prompt_wiring(source, wired, ref_fields)
            if violations:
                raise RuntimeError(f"{unit} audit failed: {violations}")
            raw["fields"]["prompt"] = wired
            (job_dir / "assets" / "prompt_h3.txt").write_text(wired, encoding="utf-8")
            (job_dir / "job.yaml").write_text(
                yaml.safe_dump(raw, allow_unicode=True, sort_keys=False, width=1000),
                encoding="utf-8",
            )

            job = load_and_validate_job(
                job_dir,
                schema_path=root / "templates" / raw["template"] / "manifest.schema.yaml",
            )
            template_dir = root / "templates" / job.template
            bindings_yaml = (template_dir / "bindings.yaml").read_text(encoding="utf-8")
            values = dict(job.fields)
            for field in list_media_fields(bindings_yaml):
                if field in job.fields:
                    values[field] = client.upload_image(job.resolve_path(field))

            use_parent = parent_latent if (load_idx and parent_latent) else None
            profile = RenderProfile(
                continuity="motion_latent",
                second_pass=False,
                save_clip_index=save_idx,
                load_clip_index=load_idx or 0,
                motion_latent_path=use_parent,
                latent_filename_prefix=LATENT_PREFIX,
            )
            unit_name = values.get("filename_prefix") or unit
            workflow = json.loads(
                (template_dir / "workflow_api.json").read_text(encoding="utf-8")
            )
            bound = prune_unused_api_ref_images(
                apply_bindings(workflow, bindings_yaml=bindings_yaml, values=values),
                values=values,
            )
            bound = apply_render_profile(bound, profile, filename_prefix=unit_name)

            job_id = uuid.uuid4().hex[:12]
            prompt_id = client.queue_prompt(bound)
            write_status(
                root / "runs" / job_id / "status.json",
                JobStatus(job_id=job_id, state="running", prompt_id=prompt_id),
            )
            print(
                f"START {unit} job={job_id} prompt={prompt_id} "
                f"save_clip={save_idx} load_clip={load_idx} parent_latent={use_parent!r}",
                flush=True,
            )
            rec: dict = {
                "unit": unit,
                "job_id": job_id,
                "prompt_id": prompt_id,
                "save_clip": save_idx,
                "load_clip": load_idx,
                "parent_latent": use_parent,
                "state": "running",
            }
            try:
                entry = wait(client, prompt_id)
                out_dir = root / "outputs" / job_id
                saved = collect_outputs(
                    client,
                    entry,
                    out_dir,
                    prefer_node_ids=preferred_video_node_ids(profile),
                )
                unit_dl = DL_ROOT / unit
                unit_dl.mkdir(parents=True, exist_ok=True)
                for p in saved:
                    (unit_dl / p.name).write_bytes(p.read_bytes())
                for name in ("prompt_h3.txt", "prompt_source.txt", "prompt_audit.json"):
                    src = job_dir / "assets" / name
                    if src.is_file():
                        (unit_dl / name).write_bytes(src.read_bytes())

                latent_path = extract_saved_latent_path(
                    entry,
                    filename_prefix=profile.latent_filename_prefix,
                    clip_index=profile.save_clip_index,
                )
                if not latent_path:
                    raise RuntimeError("could not resolve SaveLatent path")
                rel = latent_path.replace("\\", "/")
                if "/output/" in rel:
                    rel = rel.split("/output/", 1)[1]
                sub = str(PurePosixPath(rel).parent)
                name = PurePosixPath(rel).name
                if sub == ".":
                    sub = ""
                probe = client._client.get(
                    "/view",
                    params={"filename": name, "subfolder": sub, "type": "output"},
                )
                if probe.status_code >= 400:
                    raise RuntimeError(
                        f"latent missing: {rel} HTTP {probe.status_code}"
                    )
                (unit_dl / name).write_bytes(probe.content)
                latent_path = rel
                parent_latent = latent_path

                meta = {
                    "pack": "EP02-H3-zero-state-route-test-v1",
                    "continuity": "motion_latent",
                    "second_pass": False,
                    "latent_path": latent_path,
                    "prompt_id": prompt_id,
                    "job_id": job_id,
                    "save_clip": save_idx,
                    "load_clip": load_idx,
                }
                (unit_dl / "run_meta.json").write_text(
                    json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                write_status(
                    root / "runs" / job_id / "status.json",
                    JobStatus(
                        job_id=job_id,
                        state="done",
                        prompt_id=prompt_id,
                        outputs=[str(p) for p in saved],
                        message="zero-state-v1 motion_latent 一采",
                    ),
                )
                rec["state"] = "done"
                rec["outputs"] = [p.name for p in saved]
                rec["latent_path"] = latent_path
                print(
                    f"SUCCESS {unit} outputs={rec['outputs']} latent={latent_path!r}",
                    flush=True,
                )
            except Exception as e:
                write_status(
                    root / "runs" / job_id / "status.json",
                    JobStatus(
                        job_id=job_id,
                        state="failed",
                        prompt_id=prompt_id,
                        message=str(e)[:1500],
                    ),
                )
                rec["state"] = "failed"
                rec["error"] = str(e)[:800]
                print(f"FAILED {unit} {e}", flush=True)
                results.append(rec)
                batch_log.write_text(
                    json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                return 2
            results.append(rec)
            batch_log.write_text(
                json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        print(f"BATCH_DONE ok={len(results)} dir={DL_ROOT}", flush=True)
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
