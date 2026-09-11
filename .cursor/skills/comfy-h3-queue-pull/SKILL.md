---
name: comfy-h3-queue-pull
description: >-
  Queues a yz_h3_ep_unit job on remote ComfyUI, monitors queue/history with
  disconnect retry, and pulls MP4 outputs to outputs/ and optional Downloads
  compare folders. Use when submitting H3 runs, resuming after tunnel drop, or
  collecting finished films.
disable-model-invocation: true
---

# Queue → Monitor → Pull

## Goal

Execute one job on rented Comfy (H3) and land the MP4 locally.

## Prerequisite

- Phase **env** gate passed (`…:8190` + CUDA)
- Pack-jobs gate passed
- Prefer confirming bound UI only if user cares about canvas; not required for API run
- Up: `/upload/image` · Down: `/view` → `outputs/<job_id>/` (+ optional Downloads). See `../comfy-h3-ep-pipeline/reference-env.md`

## Submit options

**A. Profiled serial (preferred for EP02 A/B modes)**

```bash
export COMFY_BASE_URL=http://192.168.5.122:8190
# Confirm with user first: ref_video vs motion_latent; one-pass vs --second-pass
python scripts/run_ep_units_profiled.py --units U01 U02 --continuity ref_video \
  --download-dir /mnt/c/Users/lxy/Downloads/<dir>
```

See `docs/ops/2026-09-10-render-profiles.md` and `docs/HANDOFF.md`.

**B. CLI single job (blocks until history appears)**

```bash
export COMFY_BASE_URL=http://192.168.5.122:8190
comfy-orch submit jobs/ep_units/<EP>-<U>
```

Note: default wait timeout may be short for heavy H3; if it fails mid-wait, use resume below with the printed/`runs/*/status.json` `prompt_id`.

**C. Custom monitor (long H3)**

1. Upload + bind + `queue_prompt` (same as `runner.submit_job` up to queue)
2. Poll `/queue` + `/history/{prompt_id}` every ~10s
3. On `httpx.RemoteProtocolError`: sleep, retry poll — **do not** assume job dead
4. On `status_str=success`: `collect_outputs` → `outputs/<job_id>/`
5. Optional copy to `/mnt/c/Users/lxy/Downloads/<compare-dir>/` plus prompts / latent

Record: `runs/<job_id>/status.json` with `prompt_id`.

## Resume (after disconnect)

1. Read `runs/<job_id>/status.json` for `prompt_id`
2. If prompt_id in `/queue` running|pending → keep waiting
3. If in `/history` success → pull only
4. If **not_in_queue** and not in history after ~60s stable → report lost; ask before re-queue

## Gate (must pass)

- [ ] `prompt_id` known and status tracked
- [ ] History `success` (or explicit user cancel)
- [ ] MP4 under `outputs/<job_id>/` with size > 0
- [ ] `status.json` → `state=done` with output paths

## Timing expectations

- Pending behind another job can take many minutes
- Active H3 R2V often multi-minute; VRAM nearly full on 5090 is normal while running
- Empty history while still in `queue_running` is normal
