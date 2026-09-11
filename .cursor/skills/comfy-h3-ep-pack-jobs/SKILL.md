---
name: comfy-h3-ep-pack-jobs
description: >-
  Parses EP asset packs into yz_h3_ep_unit jobs. Supports ep02_causality
  (wire-only prompts), h3_latent (EP01), and seedance_upload (EP03/EP04).
  Use when building jobs from a pack or validating job.yaml / prompt files.
disable-model-invocation: true
---

# EP Pack → Jobs

## Goal

Turn one EP unit into `jobs/ep_units/…/` ready for bind/submit.  
Note: `jobs/` is gitignored — generate locally from the pack.

## Commands

```bash
cd /home/linux_dev/projects/comfyui-h3-automation
source .worktrees/feat-orch/.venv/bin/activate   # or .venv
python scripts/ep_pack_to_jobs.py <PACK_ROOT> -o jobs/ep_units --unit <Uxx>
```

Code: `ep_pack.build_unit_job` → for causality, `prompt_wire.wire_pack_prompt`; legacy kinds may use `h3_prompt`.

## Gate (must pass)

- [ ] Directory exists with `job.yaml`
- [ ] Template `yz_h3_ep_unit`
- [ ] **EP02 causality:** pack body kept; only media labels — run `comfy-h3-pack-prompt-audit` / `scripts/audit_pack_prompts.py`
- [ ] No leftover Windows `E:\…\assets\…` paths after wiring
- [ ] `assets/prompt_source.txt` = pack original; `assets/prompt_h3.txt` = wired/converted
- [ ] Media files in `job.yaml` exist under the job dir

## Pack kinds

- **ep02_causality**: `manifest.json` + `assets/` + `ep02/prompts/` — **wire-only**
- **h3_latent**: EP01 latent zip (`images/` + prompts)
- **seedance_upload**: EP03/EP04 `upload-manifest.json` + control/previz — may use six-section converter

## Fail

Missing pack files / parse errors / prompt audit violations → stop before export/submit.
