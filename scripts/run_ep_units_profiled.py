#!/usr/bin/env python3
"""Run EP units with selectable continuity / second-pass profiles.

Examples:
  # original behavior (MP4 parent + one pass)
  python scripts/run_ep_units_profiled.py --units U01 U02 --continuity ref_video

  # causality acceptance (latent Motion Context + 二采)
  python scripts/run_ep_units_profiled.py --units U01 U02 \\
      --continuity motion_latent --second-pass \\
      --download-dir /mnt/c/Users/lxy/Downloads/EP02-H3-causality-v21-latent-mc
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path

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


def _wait(client: ComfyClient, prompt_id: str, timeout: float = 7200.0) -> dict:
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
                raise RuntimeError(f"failed status={st} interrupted={interrupted}")
            if st == "success" or (entry.get("status") or {}).get("completed") is True:
                return entry
        q = client._client.get("/queue").json()
        run_ids = [i[1] for i in (q.get("queue_running") or []) if isinstance(i, list) and len(i) > 1]
        pen_ids = [i[1] for i in (q.get("queue_pending") or []) if isinstance(i, list) and len(i) > 1]
        state = "running" if prompt_id in run_ids else ("pending" if prompt_id in pen_ids else "not_in_queue")
        print(f"  wait {prompt_id[:8]} queue={state} elapsed={time.time()-start:.0f}s", flush=True)
        if state == "not_in_queue" and time.time() - start > 120:
            raise RuntimeError("lost from queue without history")
        if time.time() - start > timeout:
            raise TimeoutError(prompt_id)
        time.sleep(10)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--units", nargs="+", required=True, help="e.g. U01 U02")
    ap.add_argument(
        "--job-glob",
        default="EP02-H3-physical-causality-test-v2_1-20260910-{unit}",
        help="Job dir name pattern under jobs/ep_units",
    )
    ap.add_argument("--continuity", choices=("ref_video", "motion_latent"), default="ref_video")
    ap.add_argument("--second-pass", action="store_true")
    ap.add_argument("--pass2-scale", type=float, default=1.5)
    ap.add_argument(
        "--parent-latent",
        default=None,
        help="Resume motion_latent chain from this output-relative safetensors path",
    )
    ap.add_argument(
        "--download-dir",
        type=Path,
        default=Path("/mnt/c/Users/lxy/Downloads/EP02-H3-profiled"),
    )
    ap.add_argument("--batch-log", type=Path, default=None)
    args = ap.parse_args()

    root = project_root()
    base = os.environ.get("COMFY_BASE_URL", "http://192.168.5.122:8190").rstrip("/")
    dl_root = args.download_dir
    dl_root.mkdir(parents=True, exist_ok=True)
    batch_log = args.batch_log or (root / "runs" / f"profiled_{args.continuity}.json")
    results: list[dict] = []

    parent_mp4: Path | None = None
    parent_latent: str | None = args.parent_latent
    client = ComfyClient(base, timeout=180.0)
    try:
        print(
            "doctor",
            (client.system_stats().get("devices") or [{}])[0].get("name"),
            f"continuity={args.continuity} second_pass={args.second_pass}",
            flush=True,
        )
        for idx, unit in enumerate(args.units):
            job_dir = root / "jobs" / "ep_units" / args.job_glob.format(unit=unit)
            raw = yaml.safe_load((job_dir / "job.yaml").read_text(encoding="utf-8"))
            source = (job_dir / "assets" / "prompt_source.txt").read_text(encoding="utf-8")

            raw["fields"].pop("ref_video_0", None)
            if args.continuity == "ref_video" and parent_mp4 and parent_mp4.is_file():
                parent_rel = "assets/parent_prev.mp4"
                shutil.copy2(parent_mp4, job_dir / parent_rel)
                raw["fields"]["ref_video_0"] = parent_rel

            ref_fields = {k: v for k, v in raw["fields"].items() if k.startswith("ref_")}
            if args.continuity == "motion_latent":
                # Media labels only for stills; no parent video phrase injection.
                wired = wire_pack_prompt(source, {k: v for k, v in ref_fields.items() if k.startswith("ref_image_")})
            else:
                wired = wire_pack_prompt(source, ref_fields)
            violations = audit_pack_prompt_wiring(
                source,
                wired,
                {k: v for k, v in ref_fields.items() if k.startswith("ref_image_")}
                if args.continuity == "motion_latent"
                else ref_fields,
            )
            if violations:
                raise RuntimeError(f"{unit} audit failed: {violations}")
            raw["fields"]["prompt"] = wired
            (job_dir / "assets" / "prompt_h3.txt").write_text(wired, encoding="utf-8")
            (job_dir / "job.yaml").write_text(
                yaml.safe_dump(raw, allow_unicode=True, sort_keys=False, width=1000),
                encoding="utf-8",
            )

            job = load_and_validate_job(
                job_dir, schema_path=root / "templates" / raw["template"] / "manifest.schema.yaml"
            )
            template_dir = root / "templates" / job.template
            bindings_yaml = (template_dir / "bindings.yaml").read_text(encoding="utf-8")
            values = dict(job.fields)
            for field in list_media_fields(bindings_yaml):
                if field in job.fields:
                    values[field] = client.upload_image(job.resolve_path(field))

            profile = RenderProfile(
                continuity=args.continuity,
                second_pass=bool(args.second_pass),
                pass2_scale=float(args.pass2_scale),
                save_clip_index=int(unit.lstrip("Uu")),
                load_clip_index=(
                    int(unit.lstrip("Uu")) - 1
                    if args.continuity == "motion_latent" and parent_latent
                    else 0
                ),
                motion_latent_path=parent_latent,
                latent_filename_prefix=f"h3_context/ep02_{unit.lower()}",
            )
            unit_name = values.get("filename_prefix") or f"EP02-{unit}"
            workflow = json.loads((template_dir / "workflow_api.json").read_text(encoding="utf-8"))
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
                f"START {unit_name} job={job_id} prompt={prompt_id} "
                f"continuity={args.continuity} second_pass={args.second_pass} "
                f"parent_latent={parent_latent!r} parent_mp4={parent_mp4.name if parent_mp4 else None}",
                flush=True,
            )
            rec = {
                "unit": unit_name,
                "job_id": job_id,
                "prompt_id": prompt_id,
                "continuity": args.continuity,
                "second_pass": bool(args.second_pass),
                "parent_latent": parent_latent,
                "state": "running",
            }
            try:
                entry = _wait(client, prompt_id)
                out_dir = root / "outputs" / job_id
                saved = collect_outputs(
                    client,
                    entry,
                    out_dir,
                    prefer_node_ids=preferred_video_node_ids(profile),
                )
                unit_dl = dl_root / unit_name
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
                if args.continuity == "motion_latent":
                    if not latent_path:
                        raise RuntimeError("motion_latent mode could not resolve SaveLatent slot path")
                    from pathlib import PurePosixPath

                    rel = latent_path.replace("\\", "/")
                    # Normalize to output-relative slot path if Save returned absolute.
                    marker = "/output/"
                    if marker in rel:
                        rel = rel.split(marker, 1)[1]
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
                            f"motion latent slot missing on server: {rel} (HTTP {probe.status_code})"
                        )
                    (unit_dl / name).write_bytes(probe.content)
                    latent_path = rel

                meta = {
                    "continuity": args.continuity,
                    "second_pass": bool(args.second_pass),
                    "latent_path": latent_path,
                    "prompt_id": prompt_id,
                    "job_id": job_id,
                }
                (unit_dl / "run_meta.json").write_text(
                    json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
                write_status(
                    root / "runs" / job_id / "status.json",
                    JobStatus(
                        job_id=job_id,
                        state="done",
                        prompt_id=prompt_id,
                        outputs=[str(p) for p in saved],
                        message=f"profiled {args.continuity}",
                    ),
                )
                rec["state"] = "done"
                rec["outputs"] = [p.name for p in saved]
                rec["latent_path"] = latent_path
                print(f"SUCCESS {unit_name} outputs={rec['outputs']} latent={latent_path!r}", flush=True)

                if args.continuity == "motion_latent":
                    parent_latent = latent_path
                    parent_mp4 = None
                else:
                    mp4s = [p for p in saved if p.suffix.lower() == ".mp4"]
                    if not mp4s:
                        raise RuntimeError("no mp4 for parent chain")
                    pass2 = [p for p in mp4s if "pass2" in p.name.lower() or "二采" in p.name]
                    parent_mp4 = pass2[0] if pass2 else mp4s[0]
                    parent_latent = None
            except Exception as e:
                write_status(
                    root / "runs" / job_id / "status.json",
                    JobStatus(job_id=job_id, state="failed", prompt_id=prompt_id, message=str(e)[:1500]),
                )
                rec["state"] = "failed"
                rec["error"] = str(e)[:500]
                print(f"FAILED {unit_name} {e}", flush=True)
                results.append(rec)
                batch_log.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
                return 2
            results.append(rec)
            batch_log.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"BATCH_DONE ok={len(results)} dir={dl_root}", flush=True)
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
