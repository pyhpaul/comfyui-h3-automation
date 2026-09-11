---
name: comfy-h3-bound-export
description: >-
  Uploads job media to ComfyUI and exports Load-able bound UI/API JSON for the
  YZ H3 workflow without queueing. Use when the user needs to see filled slots
  or the H3 prompt on the Comfy canvas, or compare layout-preserving UI JSON.
disable-model-invocation: true
---

# Bound Workflow Export (no queue)

## Goal

Produce a **UI-format** JSON the user can **Load** in Comfy to verify media + prompt. API JSON is secondary.

## Prerequisite

- Phase **env** gate passed (`COMFY_BASE_URL=…:8190`, doctor OK)
- Phase pack-jobs gate passed
- Transfer model: upload via `POST /upload/image` into Comfy `input/`; see `../comfy-h3-ep-pipeline/reference-env.md`

## Commands

```bash
export COMFY_BASE_URL=http://192.168.5.122:8190
cd /home/linux_dev/projects/comfyui-h3-automation
source .worktrees/feat-orch/.venv/bin/activate
python scripts/export_bound_workflow.py jobs/ep_units/<EP>-<U> \
  -o "/mnt/c/Users/lxy/Downloads/<EP>-<U>-yz-bound-api.json" \
  --out-ui "/mnt/c/Users/lxy/Downloads/<EP>-<U>-yz-bound-ui.json"
```

Prefer a distinct suffix when iterating prompts (e.g. `-h3-wiring`).

## Gate (must pass)

- [ ] UI file written; size non-trivial
- [ ] UI Text / prompt node contains current `job.fields.prompt` (spot-check `<Picture 1>` / causal body for EP02; do **not** require `subject_definitions` for wire-only packs)
- [ ] Tell user: Load **UI** JSON in Comfy on **`:8190`** (same as `COMFY_BASE_URL`); API JSON rearranges layout
- [ ] Do **not** Queue unless user asks

## Note

`/prompt` never updates canvas widgets — export + Load is the only UI visibility path.
