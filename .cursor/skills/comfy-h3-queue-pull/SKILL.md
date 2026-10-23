---
name: comfy-h3-queue-pull
description: >-
  Queues a yz_h3_ep_unit job on remote ComfyUI, monitors queue/history with
  disconnect retry, and archives the four film files to Feiniu. Use when
  submitting H3 runs, resuming after tunnel drop, or checking a finished unit.
disable-model-invocation: true
---

# Queue → Monitor → Pull

## Goal

Execute one job on rented Comfy (H3). Finished films go to Feiniu, not a local download dir.

## Prerequisite

- Phase **env** gate passed (`…:8190` + CUDA)
- Pack-jobs gate passed
- Prefer confirming bound UI only if user cares about canvas; not required for API run
- Up: `/upload/image`. Finished mp4, latent, `prompt_h3.txt`, `run_meta.json` go to Feiniu. See `.cursor/rules/h3-feiniu-archive-only.mdc`.

## Submit options

**A. Profiled serial (preferred for EP02 A/B modes)**

```bash
export COMFY_BASE_URL=http://192.168.50.106:8190
export PYTHONPATH=src
# 只一采 unless they explicitly asked for 二采. Continuous scenes use motion_latent.
python scripts/run_ep_units_profiled.py --units U01 U02 \
  --continuity motion_latent \
  --feiniu-batch '<批次>'
```

`motion_latent` prints `HANDOFF` and queues the next unit before `FEINIU`. An empty `/queue` while the log still says `queue=running` is the local archive gap, not a stop. Do not re-queue a unit that is already `success` or already on Feiniu. See `.cursor/rules/h3-queue-run.mdc`.

See `docs/ops/2026-09-10-render-profiles.md` and `docs/HANDOFF.md`.

**B. CLI single job (blocks until history appears)**

```bash
export COMFY_BASE_URL=http://192.168.50.106:8190
comfy-orch submit jobs/ep_units/<EP>-<U>
```

Note: default wait timeout may be short for heavy H3; if it fails mid-wait, use resume below with the printed/`runs/*/status.json` `prompt_id`.

**C. Custom monitor (long H3)**

1. Upload + bind + `queue_prompt` (same as `runner.submit_job` up to queue)
2. Poll `/queue` + `/history/{prompt_id}` every ~10s
3. On `httpx.RemoteProtocolError`: sleep, retry poll — **do not** assume job dead
4. On `status_str=success`: archive the four film files to Feiniu, then delete the local copies under `outputs/<job_id>/`

Record: `runs/<job_id>/status.json` with `prompt_id`.

## Resume (after disconnect)

1. Read `runs/<job_id>/status.json` for `prompt_id`
2. If prompt_id in `/queue` running|pending → keep waiting
3. If in `/history` success → pull only
4. If **not_in_queue** and not in history after ~60s stable → report lost; ask before re-queue

## Gate (must pass)

- [ ] `prompt_id` known and status tracked
- [ ] History `success` (or explicit user cancel)
- [ ] Feiniu has the mp4, latent, `prompt_h3.txt`, and `run_meta.json`
- [ ] `status.json` → `state=done` with output paths

## Timing expectations

- Pending behind another job can take many minutes
- Active H3 R2V often multi-minute; VRAM nearly full on 5090 is normal while running
- Empty history while still in `queue_running` is normal
