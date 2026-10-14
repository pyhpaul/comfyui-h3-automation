---
name: comfy-h3-ep-pipeline
description: >-
  Orchestrates EP pack → YZ MiniMax H3 job → optional bound UI export → Comfy
  queue → pull MP4. Covers EP02 causality (wire-only), EP01 latent, EP03/EP04
  upload packs; one-pass vs second-pass and ref_video vs motion_latent. Use when
  running or supervising H3 out-film via vm106:8190. Project: comfyui-h3-automation.
---

# Comfy H3 EP Pipeline (Orchestrator)

## When

User wants end-to-end: asset pack → out film, or to **supervise/resume** that flow.

## Repo / env

- Root: `/home/linux_dev/projects/comfyui-h3-automation`
- Venv: `.worktrees/feat-orch/.venv` with `PYTHONPATH=src`
- `COMFY_BASE_URL` for H3: `http://192.168.50.106:8190` (vm106→GPU `:8188`) — **not** `:8188` CPU Comfy
- **Handoff (humans):** `docs/HANDOFF.md`
- Full stage doc: `docs/ops/2026-09-09-ep-pack-to-video-pipeline.md`
- **一采 vs latent+二采：** `docs/ops/2026-09-10-render-profiles.md`
- Ports & transfer: [reference-env.md](reference-env.md)
- Slot labels: [reference-wiring.md](reference-wiring.md)
- Tunnel archive: `docs/ops/2026-09-09-gpu-comfy-api-archive.md`
- vm106 tunnel scripts: `scripts/ops/`

## Supervision checklist

**Before queue/submit — do not ask the mode. Use the defaults unless this run says otherwise:**

1. Passes: **只一采**. Add `--second-pass` only when the user explicitly asks for 二采.
2. Continuity: **`motion_latent`** when the scene continues. Break the latent chain on a scene change or `start_mode=independent`. Use `ref_video` only when the user explicitly asks for 整片参考.

Copy and tick:

```
EP pipeline:
- [ ] 0 Env/doctor  (comfy-h3-env) — COMFY_BASE_URL=:8190, CUDA ok
- [ ] 0b Mode gate — 只一采 unless 二采 was explicit; motion_latent on continuous scenes, chain broken on cuts and independent units
- [ ] 1 Pack→Job     (comfy-h3-ep-pack-jobs)
- [ ] 1b Prompt audit (comfy-h3-pack-prompt-audit) before any serial queue
- [ ] 2 Bound export (comfy-h3-bound-export) — skip if user said API-only / no UI check
- [ ] 3 Queue+pull   (profiled script or comfy-h3-queue-pull)
- [ ] 4 Report prompt_id and the Feiniu archive path
```

**Rules**

1. Always run phase **0** before upload/submit.
2. Read and follow each phase skill **before** that phase’s commands.
3. Do not start the next phase until the phase gate passes.
4. Single GPU serial: enqueue is OK while another job runs; do not assume multi-GPU.
5. On tunnel/`RemoteProtocolError`: **resume by prompt_id** — do not double-submit unless queue lost the job.
6. Do not batch whole episodes or change LoRA/steps unless the user asks.
7. **Render mode:** 只一采 unless the user explicitly asks for 二采. Continuous scenes use `motion_latent`; do not switch to `ref_video` unless they explicitly ask. Prefer `scripts/run_ep_units_profiled.py`. Finished films go to Feiniu.
8. Prompt: EP02 causality = wire-only (`comfy-h3-pack-prompt-audit`); do not require six-section English for those packs.
9. Up/down is HTTP API via Base URL (not ad-hoc scp) for normal EP media.
10. Tunnel lives on **vm106** `192.168.50.106:8190`. Deploy and shutdown: `.cursor/rules/h3-gpu-vm106.mdc`.

## Phase dispatch

| Phase | Skill path |
|-------|------------|
| 0 | `.cursor/skills/comfy-h3-env/SKILL.md` |
| 1 | `.cursor/skills/comfy-h3-ep-pack-jobs/SKILL.md` |
| 1b | `.cursor/skills/comfy-h3-pack-prompt-audit/SKILL.md` |
| 2 | `.cursor/skills/comfy-h3-bound-export/SKILL.md` |
| 3 | `.cursor/skills/comfy-h3-queue-pull/SKILL.md` (+ `scripts/run_ep_units_profiled.py`) |

## Done report (required)

Tell the user:

- Mode: continuity + whether second-pass
- `job_dir` / units, `job_id`, `prompt_id`
- Feiniu path for the mp4, latent, `prompt_h3.txt`, and `run_meta.json`
- Whether bound UI was exported and its path
