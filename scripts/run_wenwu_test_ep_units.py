#!/usr/bin/env python3
"""TEST runner for 文武双全 SelfLift template — does not touch yz_h3_ep_unit.

Both U01/U02 in the mafia EP01 pack are start_mode=independent, so there is
no motion_latent handoff between them. Each unit still saves a latent for the
Feiniu four-file archive.

Usage:
  COMFY_BASE_URL=http://192.168.50.106:8190 PYTHONPATH=src \\
  python scripts/run_wenwu_test_ep_units.py \\
    --units U01 U02 \\
    --feiniu-batch '<新批次名>'
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path, PurePosixPath

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comfy_orch.artifacts import collect_outputs  # noqa: E402
from comfy_orch.binder import apply_bindings, list_media_fields  # noqa: E402
from comfy_orch.client import ComfyClient  # noqa: E402
from comfy_orch.feiniu_archive import archive_named_files  # noqa: E402
from comfy_orch.manifest import load_and_validate_job  # noqa: E402
from comfy_orch.named_assets_bind import motion_latent_prefix  # noqa: E402
from comfy_orch.prompt_wire import audit_pack_prompt_wiring, wire_pack_prompt  # noqa: E402
from comfy_orch.render_profile import extract_saved_latent_path  # noqa: E402
from comfy_orch.ui_bind import prune_unused_api_ref_images  # noqa: E402

TEMPLATE = "yz_h3_wenwu_test"
JOB_ROOT = ROOT / "jobs" / "ep_units_wenwu_test"
LATENT_ROOT = "h3_context/wenwu_test"


def _wait_history(client: ComfyClient, prompt_id: str, unit_name: str) -> dict:
    t0 = time.monotonic()
    print(f"WAIT {unit_name} prompt_id={prompt_id}", flush=True)
    # H3 SelfLift on 5090 can take well over 10 minutes.
    entry = client.wait_until_done(prompt_id, poll_interval=10.0, timeout=7200.0)
    status = ((entry.get("status") or {}).get("status_str") or "").lower()
    if status in {"error", "failed"}:
        raise RuntimeError(f"{unit_name} failed: {entry.get('status')}")
    # wait_until_done returns at first history sight; poll until outputs exist.
    while not entry.get("outputs") and status not in {"success", "error", "failed"}:
        time.sleep(10)
        entry = client.wait_until_done(prompt_id, poll_interval=5.0, timeout=120.0)
        status = ((entry.get("status") or {}).get("status_str") or "").lower()
        print(
            f"WAIT {unit_name} status={status!r} elapsed={time.monotonic() - t0:.0f}s",
            flush=True,
        )
    if status in {"error", "failed"} or not entry.get("outputs"):
        raise RuntimeError(f"{unit_name} incomplete: status={status!r}")
    print(
        f"DONE {unit_name} status={status!r} elapsed={time.monotonic() - t0:.0f}s",
        flush=True,
    )
    return entry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--units", nargs="+", required=True)
    ap.add_argument("--feiniu-batch", required=True)
    ap.add_argument(
        "--job-prefix",
        default="EP01-黑手党老大-v2",
        help="Directory name prefix under jobs/ep_units_wenwu_test",
    )
    args = ap.parse_args()
    batch = (args.feiniu_batch or "").strip()
    if not batch:
        raise SystemExit("need --feiniu-batch")

    base = os.environ.get("COMFY_BASE_URL") or "http://192.168.50.106:8190"
    client = ComfyClient(base)
    stats = client.system_stats()
    device = ((stats.get("devices") or [{}])[0].get("name")) or ""
    # Do not apply_gpu_profile here — that helper hardcodes yz_h3_ep_unit node ids.
    # This TEST graph already has MiniMaxLowVRAMAttention / attention nodes.
    print(
        f"READY base={base} gpu={device!r} "
        f"template={TEMPLATE} feiniu_batch={batch!r}",
        flush=True,
    )

    template_dir = ROOT / "templates" / TEMPLATE
    workflow_base = json.loads((template_dir / "workflow_api.json").read_text(encoding="utf-8"))
    bindings_yaml = (template_dir / "bindings.yaml").read_text(encoding="utf-8")
    schema = template_dir / "manifest.schema.yaml"

    for unit in args.units:
        unit = unit.strip().upper()
        job_dir = JOB_ROOT / f"{args.job_prefix}-{unit}"
        if not job_dir.is_dir():
            raise SystemExit(f"missing job dir {job_dir}")

        raw = yaml.safe_load((job_dir / "job.yaml").read_text(encoding="utf-8"))
        source = (job_dir / "assets" / "prompt_source.txt").read_text(encoding="utf-8")
        ref_fields = {
            k: v for k, v in (raw.get("fields") or {}).items() if k.startswith("ref_image_")
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

        job = load_and_validate_job(job_dir, schema_path=schema)
        if job.template != TEMPLATE:
            raise SystemExit(f"{job_dir} template={job.template} want {TEMPLATE}")

        values = dict(job.fields)
        for field in list_media_fields(bindings_yaml):
            if field in job.fields:
                values[field] = client.upload_image(job.resolve_path(field))

        episode = str(raw.get("episode") or "")
        unit_name = values.get("filename_prefix") or f"{episode}-{unit}"
        latent_prefix = f"{LATENT_ROOT}/{motion_latent_prefix(episode, unit)}"

        workflow = json.loads(json.dumps(workflow_base))
        if "9001" in workflow:
            workflow["9001"]["inputs"]["filename_prefix"] = latent_prefix

        bound = prune_unused_api_ref_images(
            apply_bindings(workflow, bindings_yaml=bindings_yaml, values=values),
            values=values,
        )
        # Drop empty media loaders left over from the UI template so Comfy
        # does not validate audio/video=None placeholders.
        keep: dict = {}
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
        # Guard: 265 must receive a non-empty prompt (link to 263 or literal).
        p_in = (bound.get("265", {}).get("inputs") or {}).get("prompt")
        resolved = ""
        if isinstance(p_in, list) and len(p_in) == 2:
            src = bound.get(str(p_in[0]), {}).get("inputs") or {}
            resolved = str(src.get("text") or "")
        elif isinstance(p_in, str):
            resolved = p_in
        if not resolved.strip():
            raise RuntimeError(f"{unit_name}: 265 prompt resolves empty; refusing to queue")
        if "364" in bound:
            bound["364"]["inputs"]["filename_prefix"] = f"{unit_name}-wenwu"
            bound["364"]["inputs"]["save_output"] = True

        print(
            f"QUEUE {unit_name} start_mode={raw.get('start_mode')!r} "
            f"upscaler={bound.get('397', {}).get('inputs', {}).get('upscaler_model')} "
            f"tiling={bound.get('397', {}).get('inputs', {}).get('highres_tiling')}",
            flush=True,
        )
        prompt_id = client.queue_prompt(bound)
        print(f"QUEUED {unit_name} prompt_id={prompt_id}", flush=True)
        entry = _wait_history(client, prompt_id, unit_name)

        out_dir = ROOT / "outputs" / prompt_id
        saved = collect_outputs(client, entry, out_dir, prefer_node_ids=["364"])
        latent_path = extract_saved_latent_path(
            entry, filename_prefix=latent_prefix, clip_index=1
        )
        if not latent_path:
            raise RuntimeError(f"{unit_name}: missing motion latent path in history")
        rel = latent_path
        if "output/" in rel:
            rel = rel.split("output/", 1)[1]
        sub = str(PurePosixPath(rel).parent)
        name = PurePosixPath(rel).name
        if sub == ".":
            sub = ""
        probe = client._client.get(
            "/view", params={"filename": name, "subfolder": sub, "type": "output"}
        )
        if probe.status_code >= 400:
            raise RuntimeError(f"latent download HTTP {probe.status_code}")

        meta = {
            "continuity": "independent",
            "second_pass": False,
            "template": TEMPLATE,
            "upscaler": "minimax_h3_latent_upscaler_3d_fp16.safetensors",
            "highres_tiling": False,
            "latent_path": rel,
            "prompt_id": prompt_id,
            "test": "wenwu_selflift_v1",
            "source_job": str(job_dir.relative_to(ROOT)),
        }
        payloads = {
            path.name: path.read_bytes() for path in saved if path.suffix.lower() == ".mp4"
        }
        if not payloads:
            raise RuntimeError(f"{unit_name}: no mp4 in outputs {[p.name for p in saved]}")
        payloads["prompt_h3.txt"] = (job_dir / "assets" / "prompt_h3.txt").read_bytes()
        payloads["run_meta.json"] = (
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        payloads[name] = probe.content
        remote = archive_named_files(
            payloads, batch=batch, episode=episode, unit=unit
        )
        print(f"FEINIU {unit_name} {remote}", flush=True)
        print(f"SUCCESS {unit_name} prompt_id={prompt_id} latent={rel}", flush=True)
        if out_dir.is_dir():
            shutil.rmtree(out_dir, ignore_errors=True)

    print("BATCH_DONE wenwu_test", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
