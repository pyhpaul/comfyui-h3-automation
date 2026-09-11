---
name: comfy-h3-pack-prompt-audit
description: >-
  Audits EP pack → job prompt wiring: keep pack prompt text unchanged except
  replacing reference image/video paths with <Picture N>/<Video 1>. Use before
  submit, after ep_pack_to_jobs, or when prompts look hollow/identical across units.
  Hard gate: always preflight BOTH no-parent and simulated-parent paths for serial.
---

# Pack Prompt Audit（资产包提示词审核）

## Rule (hard)

1. **Keep pack prompt body as-is** (Chinese/English, shots, causality, dialogue).
2. **Only allowed edit:** replace reference media path/name tokens with H3 labels:
   - stills in job order → `<Picture 1>`, `<Picture 2>`, …
   - parent/previz video when present → `<Video 1>` (or inject one media line `父片段：<Video 1>` under 接入文字)
3. **Forbidden:** English six-section rewrite, CJK stripping, summarizing shots, inventing new beats.
4. **Forbidden parent rewrite:** never turn `保存原始 H3 AV latent` into `保存<Video 1>`.
5. Experiment note: language (EN vs ZH) is not the quality lever; **media label wiring + intact causal text** is.

## Why disk `prompt_audit.json` alone is insufficient

`build_unit_job` audits **without** `ref_video_0`. Serial U02+ only attach `parent_prev.mp4` at submit time. Auditing only the build-time JSON **misses** parent-path regressions (this already broke a live U02 submit once).

**Gate rule for agents:** before any U01–Un serial queue, run the preflight script (or `preflight_job_dir(..., require_parent_path=True)`). Do not claim “audit passed” from `prompt_audit.json` alone.

## When

- Building jobs from EP02 causality (and any pack where TXT is already H3-ready)
- **Immediately before** queue/submit of a serial chain
- When two units look alike and prompts may have been gutted by converters

## Procedure (required before serial submit)

```bash
cd /home/linux_dev/projects/comfyui-h3-automation
source .worktrees/feat-orch/.venv/bin/activate
python scripts/audit_pack_prompts.py
# optional: python scripts/audit_pack_prompts.py jobs/ep_units/<JOB> --json
```

Exit code must be `0`. Script exercises:

1. **no_parent** — current job refs (build-time path)
2. **with_parent** — same refs + simulated `assets/parent_prev.mp4`

Code path:

- `comfy_orch.prompt_wire.wire_pack_prompt`
- `comfy_orch.prompt_wire.audit_pack_prompt_wiring`
- `comfy_orch.prompt_wire.preflight_job_dir`
- `ep_pack.build_unit_job` for `pack_kind=ep02_causality` writes build-time `assets/prompt_audit.json` (no-parent only)

## Gate (must pass)

- [ ] `python scripts/audit_pack_prompts.py` → all units PASS (no_parent **and** with_parent)
- [ ] `prompt_source.txt` preserves pack unit TXT intent (no rewrite)
- [ ] Every used `ref_image_*` has matching `<Picture N>` in wired prompt
- [ ] Simulated/real `ref_video_0` → `<Video 1>` present; `保存原始 H3 AV latent` unchanged
- [ ] No leftover `E:\...\assets\...` Windows paths
- [ ] Causal / 逐镜 body still readable
- [ ] Do **not** require `subject_definitions:` six-section English
- [ ] Warnings (e.g. unbound relative asset like U07 crystal) are acknowledged; do not treat warning-only as PASS for missing Picture slots if the asset is required for the shot

## Fail

Any body edit beyond media labels, or parent path audit failure → **stop submit**; fix `prompt_wire` / rebuild; re-run preflight.

## Related

- Pack→jobs: `comfy-h3-ep-pack-jobs`
- Queue: `comfy-h3-queue-pull`
- Wiring table: `comfy-h3-ep-pipeline/reference-wiring.md` (labels still apply; six-section English is optional/legacy)
