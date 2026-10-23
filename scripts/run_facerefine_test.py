#!/usr/bin/env python3
"""Queue one FaceRefine post-pass on a finished mp4. TEST-ONLY.

Requires:
  - GPU Comfy up on :8190 with FaceRefine nodes loaded
  - templates/yz_h3_facerefine_test/workflow_api.json exported from UI
    (placeholder {} means prep not finished — this script refuses)

Usage (after prep + API export):
  PYTHONPATH=src COMFY_BASE_URL=http://192.168.50.106:8190 \\
    python scripts/run_facerefine_test.py \\
      --video jobs/facerefine_test/source_U01/<clip>.mp4 \\
      --prompt-file jobs/facerefine_test/source_U01/prompt_h3.txt \\
      --feiniu-batch '<新批次>' \\
      --episode EP01 --unit U01
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comfy_orch.artifacts import collect_outputs  # noqa: E402
from comfy_orch.client import ComfyClient  # noqa: E402
from comfy_orch.feiniu_archive import archive_named_files  # noqa: E402

TEMPLATE = ROOT / "templates" / "yz_h3_facerefine_test"
NEEDED_NODES = (
    "H3FaceTrackCrop",
    "H3FaceStitch",
    "H3InjectVideoLatent",
    "H3PerFrameDenoise",
)


def _load_api_workflow() -> dict:
    path = TEMPLATE / "workflow_api.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not raw or set(raw.keys()) <= {"id"}:
        raise SystemExit(
            f"{path} is still a placeholder. Open "
            f"{TEMPLATE / 'workflow_ui.auto_select.source.json'} in Comfy UI, "
            "rebind H3 models + source video, Save (API Format), overwrite this file."
        )
    # API format: node-id → {class_type, inputs}
    sample = next(iter(raw.values()))
    if not isinstance(sample, dict) or "class_type" not in sample:
        raise SystemExit(f"{path} does not look like Comfy API format")
    return raw


def _preflight(client: ComfyClient) -> None:
    stats = client.system_stats()
    device = ((stats.get("devices") or [{}])[0].get("name")) or ""
    if not device:
        raise SystemExit("no CUDA device in /system_stats")
    r = client._client.get("/object_info")
    r.raise_for_status()
    info = r.json()
    missing = [n for n in NEEDED_NODES if n not in info]
    if missing:
        raise SystemExit(
            f"FaceRefine nodes missing on Comfy: {missing}. "
            "Run scripts/ops/install_facerefine_gpu.py --pip and restart Comfy."
        )
    print(f"PREFLIGHT ok gpu={device!r} nodes={list(NEEDED_NODES)}", flush=True)


def _bind_video_and_prompt(workflow: dict, video_name: str, prompt: str) -> dict:
    """Best-effort: set video path / prompt on known class types."""
    out = json.loads(json.dumps(workflow))
    for _nid, node in out.items():
        ct = node.get("class_type")
        inputs = node.setdefault("inputs", {})
        if ct in {"VHS_LoadVideoPath", "VHS_LoadVideo"}:
            for key in ("video", "file", "path"):
                if key in inputs or ct == "VHS_LoadVideoPath":
                    inputs["video" if "video" in inputs or key == "video" else key] = video_name
                    break
            if "video" not in inputs and "file" not in inputs:
                inputs["video"] = video_name
        if ct == "MiniMaxH3ReferenceToVideo" and "prompt" in inputs:
            inputs["prompt"] = prompt
        if ct == "VHS_VideoCombine":
            inputs["filename_prefix"] = inputs.get("filename_prefix") or "facerefine_test"
            inputs["save_output"] = True
    return out


def _wait(client: ComfyClient, prompt_id: str) -> dict:
    print(f"WAIT prompt_id={prompt_id}", flush=True)
    t0 = time.monotonic()
    entry = client.wait_until_done(prompt_id, poll_interval=10.0, timeout=7200.0)
    status = ((entry.get("status") or {}).get("status_str") or "").lower()
    while not entry.get("outputs") and status not in {"success", "error", "failed"}:
        time.sleep(10)
        entry = client.wait_until_done(prompt_id, poll_interval=5.0, timeout=120.0)
        status = ((entry.get("status") or {}).get("status_str") or "").lower()
        print(f"WAIT status={status!r} elapsed={time.monotonic() - t0:.0f}s", flush=True)
    if status in {"error", "failed"} or not entry.get("outputs"):
        raise RuntimeError(f"incomplete: status={status!r}")
    print(f"DONE status={status!r} elapsed={time.monotonic() - t0:.0f}s", flush=True)
    return entry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, type=Path)
    ap.add_argument("--prompt-file", required=True, type=Path)
    ap.add_argument("--feiniu-batch", required=True)
    ap.add_argument("--episode", default="EP01")
    ap.add_argument("--unit", default="U01")
    args = ap.parse_args()

    batch = (args.feiniu_batch or "").strip()
    if not batch:
        raise SystemExit("need --feiniu-batch")
    if not args.video.is_file():
        raise SystemExit(f"missing video {args.video}")
    prompt = args.prompt_file.read_text(encoding="utf-8")

    workflow = _load_api_workflow()
    base = os.environ.get("COMFY_BASE_URL") or "http://192.168.50.106:8190"
    client = ComfyClient(base)
    _preflight(client)

    # Upload into Comfy input/ (same endpoint as images; filename kept).
    video_name = client.upload_image(args.video)
    print(f"UPLOADED video={video_name!r}", flush=True)
    bound = _bind_video_and_prompt(workflow, video_name, prompt)

    print(f"QUEUE facerefine {args.episode}-{args.unit} batch={batch!r}", flush=True)
    prompt_id = client.queue_prompt(bound)
    print(f"QUEUED prompt_id={prompt_id}", flush=True)
    entry = _wait(client, prompt_id)

    out_dir = ROOT / "outputs" / prompt_id
    saved = collect_outputs(client, entry, out_dir)
    mp4s = [p for p in saved if p.suffix.lower() == ".mp4"]
    if not mp4s:
        raise RuntimeError(f"no mp4 in outputs {[p.name for p in saved]}")

    meta = {
        "test": "facerefine_postpass",
        "template": "yz_h3_facerefine_test",
        "source_video": str(args.video),
        "source_batch_hint": "文武双全TEST-黑手党EP01（10.19）",
        "prompt_id": prompt_id,
        "second_pass": False,
        "continuity": "independent",
    }
    # FaceRefine archive: mp4 + prompt + meta; pad with a tiny placeholder
    # latent so Feiniu still gets the four-file layout the share expects.
    latent_name = f"{args.unit}-facerefine.placeholder.safetensors"
    payloads = {
        mp4s[0].name: mp4s[0].read_bytes(),
        "prompt_h3.txt": prompt.encode("utf-8"),
        "run_meta.json": (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        ),
        latent_name: b"FACEREFINE_NO_LATENT\n",
    }
    remote = archive_named_files(
        payloads, batch=batch, episode=args.episode, unit=args.unit
    )
    print(f"FEINIU {args.episode}-{args.unit} {remote}", flush=True)
    print(f"SUCCESS prompt_id={prompt_id}", flush=True)
    if out_dir.is_dir():
        shutil.rmtree(out_dir, ignore_errors=True)
    print("BATCH_DONE facerefine_test", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
