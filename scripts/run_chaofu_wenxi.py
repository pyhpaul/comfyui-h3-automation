#!/usr/bin/env python3
"""Render Chaofu fix units through the wenwu WENXI chain for A/B compare.

Same jobs/prompts/assets as the original-workflow fix renders, but bound
into templates/yz_h3_wenwu_test/variants/wenxi (combat/fight-flow/speed
LoRAs at 0). The stock wenwu graph has no parent-latent input, so for
start_mode=parent_latent units we graft the same three nodes the
yz_h3_ep_unit profile uses (MiniMaxH3MotionContextLoadLatent 9101 ->
MiniMaxH3MotionContext 9102 -> MiniMaxH3MotionContextTrim 9103) and feed
SelfLift's positive conditioning from the motion-context node.

Within one invocation, chained units automatically consume the previous
unit's saved latent (h3_context/chaofu_wenxi/...); independent units
reset. Outputs go to Feiniu batch under unit dir '<U>-WENXI' with
'-wenxi' file names so they never collide with the original-workflow
renders in '<U>'.

Usage:
  COMFY_BASE_URL=http://192.168.50.106:8190 PYTHONPATH=src \
    python scripts/run_chaofu_wenxi.py --job-prefix 'EP23-潮缚-fix1' \
      --units U05 --parent-latent h3_context/ep23_u04_00004.safetensors \
      --feiniu-batch '潮缚修复（10.20）'
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import random
import shutil
import sys
import threading
import time
from pathlib import Path, PurePosixPath

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from comfy_orch.artifacts import collect_outputs  # noqa: E402
from comfy_orch.binder import apply_bindings, list_media_fields  # noqa: E402
from comfy_orch.client import ComfyClient  # noqa: E402
from comfy_orch.feiniu_archive import archive_named_files  # noqa: E402
from comfy_orch.manifest import load_and_validate_job  # noqa: E402
from comfy_orch.prompt_wire import audit_pack_prompt_wiring, wire_pack_prompt  # noqa: E402
from comfy_orch.render_profile import extract_saved_latent_path  # noqa: E402
from comfy_orch.ui_bind import prune_unused_api_ref_images  # noqa: E402
from run_wenwu_test_ep_units import _wait_history  # noqa: E402

TEMPLATE_DIR = ROOT / "templates" / "yz_h3_wenwu_test"
WORKFLOW = TEMPLATE_DIR / "variants" / "wenxi" / "workflow_api.json"
JOB_ROOT = ROOT / "jobs" / "ep_units"
LATENT_ROOT = "h3_context/chaofu_wenxi"

LOAD_ID, MOTION_ID, TRIM_ID = "9101", "9102", "9103"


def frame_length(duration_seconds: float) -> int:
    n = max(5, round(duration_seconds * 24))
    return n + (5 - (n % 17)) % 17


def unit_index(unit: str) -> int:
    return int(unit.strip("Uu"))


def graft_motion_latent(workflow: dict, parent_latent: str, load_clip: int) -> None:
    workflow[LOAD_ID] = {
        "class_type": "MiniMaxH3MotionContextLoadLatent",
        "inputs": {"latent_path": parent_latent, "clip_index": load_clip},
        "_meta": {"title": "H3 Motion Context Load Latent (wenxi graft)"},
    }
    workflow[MOTION_ID] = {
        "class_type": "MiniMaxH3MotionContext",
        "inputs": {
            "conditioning": ["265", 0],
            "vae": ["36", 0],
            "latent": ["265", 1],
            "context_length": "22",
            "audio_context_length": 24,
            "context_latent": [LOAD_ID, 0],
            "audio_vae": ["37", 0],
        },
        "_meta": {"title": "MiniMax H3 Motion Context (wenxi graft)"},
    }
    workflow["397"]["inputs"]["positive"] = [MOTION_ID, 0]
    workflow[TRIM_ID] = {
        "class_type": "MiniMaxH3MotionContextTrim",
        "inputs": {
            "images": ["253", 0],
            "trim_frames": [MOTION_ID, 1],
            "audio": ["254", 0],
            "fps": 24.0,
            "match_tail": True,
        },
        "_meta": {"title": "H3 Motion Context Trim (wenxi graft)"},
    }
    workflow["364"]["inputs"]["images"] = [TRIM_ID, 0]
    workflow["364"]["inputs"]["audio"] = [TRIM_ID, 1]


def _archive_worker(base: str, tasks: "queue.Queue[dict | None]",
                    errors: list[str]) -> None:
    """Single background worker: download mp4+latent, then Feiniu/local.

    Per h3-queue-run.mdc, the main loop must HANDOFF and queue the next
    unit as soon as history exposes the GPU latent path; downloads and
    archive uploads happen here, never blocking the next queue_prompt.
    """
    client = ComfyClient(base)
    while True:
        task = tasks.get()
        try:
            if task is None:
                return
            label = f"{task['ep_code']}-{task['unit']}"
            saved = collect_outputs(client, task["entry"],
                                    ROOT / "outputs" / task["prompt_id"],
                                    prefer_node_ids=["364"])
            mp4s = [p for p in saved if p.suffix.lower() == ".mp4"]
            if not mp4s:
                raise RuntimeError(f"{label}: no mp4")
            rel = task["latent_rel"]
            sub = str(PurePosixPath(rel).parent)
            if sub == ".":
                sub = ""
            probe = client._client.get(
                "/view", params={"filename": PurePosixPath(rel).name,
                                 "subfolder": sub, "type": "output"})
            if probe.status_code >= 400:
                raise RuntimeError(f"latent download HTTP {probe.status_code}")
            meta = task["meta"]
            payloads = {
                f"{label}-chaofu-wenxi_00001-audio.mp4":
                    mp4s[0].read_bytes(),
                f"{task['ep_code'].lower()}_{task['unit'].lower()}"
                f"_wenxi_00001.safetensors": probe.content,
                "prompt_h3.txt": task["wired"].encode("utf-8"),
                "run_meta.json": (json.dumps(meta, ensure_ascii=False,
                                             indent=2) + "\n").encode("utf-8"),
            }
            if task["local_only"]:
                dest = (ROOT / ".cache" / "chaofu_fix1_verify"
                        / label / "wenxi")
                dest.mkdir(parents=True, exist_ok=True)
                for name, data in payloads.items():
                    (dest / name).write_bytes(data)
                print(f"LOCAL_SAVED {label} wenxi -> {dest}", flush=True)
            else:
                remote = archive_named_files(
                    payloads, batch=task["feiniu_batch"],
                    episode=task["episode"], unit=f"{task['unit']}-WENXI")
                print(f"FEINIU {label}-wenxi {remote}", flush=True)
            print(f"SUCCESS {label} wenxi prompt_id={task['prompt_id']} "
                  f"latent={rel} elapsed={meta['elapsed_s']}s", flush=True)
            out_dir = ROOT / "outputs" / task["prompt_id"]
            if out_dir.is_dir():
                shutil.rmtree(out_dir, ignore_errors=True)
        except Exception as exc:  # surfaced to main before next queue
            errors.append(f"{task['ep_code']}-{task['unit']}: {exc}")
            print(f"ARCHIVE_FAILED {exc}", flush=True)
        finally:
            tasks.task_done()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-prefix", required=True,
                    help="e.g. EP23-潮缚-fix1 or EP62-潮缚-v1")
    ap.add_argument("--units", nargs="+", required=True)
    ap.add_argument("--parent-latent", default=None,
                    help="output-relative parent latent for the first "
                         "parent_latent unit in --units")
    ap.add_argument("--feiniu-batch", default=None)
    ap.add_argument("--local-only", action="store_true",
                    help="save payloads under .cache/chaofu_fix1_verify "
                         "instead of uploading to Feiniu (audit-first)")
    ap.add_argument("--seed", type=int, default=None,
                    help="fixed seed (default: random per unit, recorded "
                         "in run_meta.json)")
    args = ap.parse_args()

    workflow_base = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    bindings_yaml = (TEMPLATE_DIR / "bindings.yaml").read_text(encoding="utf-8")
    schema = TEMPLATE_DIR / "manifest.schema.yaml"

    base = os.environ.get("COMFY_BASE_URL") or "http://192.168.50.106:8190"
    client = ComfyClient(base)
    device = ((client.system_stats().get("devices") or [{}])[0].get("name")) or ""
    if not device:
        raise SystemExit("no CUDA device")
    print(f"READY gpu={device!r} chain=wenxi prefix={args.job_prefix}", flush=True)

    parent_latent: str | None = args.parent_latent
    archive_tasks: "queue.Queue[dict | None]" = queue.Queue()
    archive_errors: list[str] = []
    worker = threading.Thread(
        target=_archive_worker, args=(base, archive_tasks, archive_errors),
        name="chaofu-wenxi-archive", daemon=True)
    worker.start()
    for unit in args.units:
        if archive_errors:
            # h3-queue-run.mdc: a failed background archive stops the batch
            print(f"ARCHIVE_FAILED stop before {unit}: {archive_errors}",
                  flush=True)
            break
        unit = unit.strip().upper()
        job_dir = JOB_ROOT / f"{args.job_prefix}-{unit}"
        if not job_dir.is_dir():
            raise SystemExit(f"missing job dir {job_dir}")
        raw = yaml.safe_load((job_dir / "job.yaml").read_text(encoding="utf-8"))
        source = (job_dir / "assets" / "prompt_source.txt").read_text(encoding="utf-8")
        ref_fields = {k: v for k, v in (raw.get("fields") or {}).items()
                      if k.startswith("ref_image_")}
        wired = wire_pack_prompt(source, ref_fields)
        violations = audit_pack_prompt_wiring(source, wired, ref_fields)
        if violations:
            raise RuntimeError(f"{job_dir.name} audit failed: {violations}")
        raw["fields"]["prompt"] = wired

        job = load_and_validate_job(job_dir, schema_path=schema)
        values = dict(job.fields)
        for field in list_media_fields(bindings_yaml):
            if field in job.fields:
                values[field] = client.upload_image(job.resolve_path(field))

        episode = str(raw.get("episode") or "")
        ep_code = episode.split("-")[0]
        start_mode = str(raw.get("start_mode") or "independent")
        if start_mode == "independent":
            parent_latent = None
        duration = float(values.get("duration_seconds") or 15.083)
        latent_prefix = f"{LATENT_ROOT}/{ep_code.lower()}_{unit.lower()}"

        workflow = json.loads(json.dumps(workflow_base))
        workflow["9001"]["inputs"]["filename_prefix"] = latent_prefix
        workflow["9001"]["inputs"]["clip_index"] = unit_index(unit)
        bound = prune_unused_api_ref_images(
            apply_bindings(workflow, bindings_yaml=bindings_yaml, values=values),
            values=values)
        keep = {}
        for nid, node in bound.items():
            ct = node.get("class_type")
            inputs = node.get("inputs") or {}
            if ct == "LoadAudio" and inputs.get("audio") in (None, "None", ""):
                continue
            if ct == "VHS_LoadVideo" and not inputs.get("video"):
                continue
            if ct == "LoadImage" and inputs.get("image") in (None, "None", ""):
                continue
            keep[nid] = node
        bound = keep
        bound["265"]["inputs"]["prompt"] = wired
        # match yz_h3_ep_unit output (768x1376) so parent latents align
        bound["265"]["inputs"]["width"] = 768
        bound["265"]["inputs"]["height"] = 1376
        bound["265"]["inputs"]["length"] = frame_length(duration)
        seed = (args.seed if args.seed is not None
                else random.randrange(0, 2**63 - 1))
        bound["397"]["inputs"]["seed"] = seed
        bound["364"]["inputs"]["filename_prefix"] = (
            f"{ep_code}-{unit}-chaofu-wenxi")
        bound["364"]["inputs"]["save_output"] = True
        if parent_latent:
            graft_motion_latent(bound, parent_latent, unit_index(unit) - 1)

        print(f"QUEUE {ep_code}-{unit} wenxi start={start_mode} "
              f"parent={parent_latent!r} frames={bound['265']['inputs']['length']}",
              flush=True)
        t0 = time.monotonic()
        prompt_id = client.queue_prompt(bound)
        print(f"QUEUED {ep_code}-{unit} prompt_id={prompt_id}", flush=True)
        entry = _wait_history(client, prompt_id, f"{ep_code}-{unit}-wenxi")

        # HANDOFF point (h3-queue-run.mdc): history exposing the GPU
        # latent path is enough to queue the next unit. Downloading the
        # mp4/latent and the Feiniu upload run in the archive worker.
        latent_rel = extract_saved_latent_path(
            entry, filename_prefix=latent_prefix, clip_index=unit_index(unit))
        if not latent_rel:
            raise RuntimeError(f"{ep_code}-{unit}: missing saved latent path")
        rel = latent_rel.split("output/", 1)[-1]

        meta = {
            "continuity": "motion_latent" if parent_latent else "independent",
            "second_pass": False,
            "template": "yz_h3_wenwu_test/wenxi",
            "chain": "wenxi",
            "seed": seed,
            "parent_latent": parent_latent,
            "latent_path": rel,
            "prompt_id": prompt_id,
            "source_job": str(job_dir.relative_to(ROOT)),
            "elapsed_s": round(time.monotonic() - t0),
        }
        if not args.local_only and not args.feiniu_batch:
            raise SystemExit("need --feiniu-batch unless --local-only")
        archive_tasks.put({
            "ep_code": ep_code, "unit": unit, "prompt_id": prompt_id,
            "entry": entry, "latent_rel": rel, "wired": wired,
            "meta": meta, "episode": episode,
            "feiniu_batch": args.feiniu_batch,
            "local_only": args.local_only,
        })
        print(f"HANDOFF {ep_code}-{unit} latent={rel!r}", flush=True)
        # chain: next parent_latent unit consumes this unit's latent
        parent_latent = rel
    archive_tasks.join()
    archive_tasks.put(None)
    worker.join()
    if archive_errors:
        print(f"BATCH_ARCHIVE_FAILED {archive_errors}", flush=True)
        return 1
    print(f"BATCH_DONE wenxi {args.job_prefix}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
