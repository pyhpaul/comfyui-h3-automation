# A100 U02 attention A/B: one-session execution preparation

Status: this was the pre-execution contract. The authorized formal A/B ran on
2026-09-25; see `2026-09-25-h3-a100-ab-results.md` for measured results,
transport incident, cost, and shutdown evidence. This document complements
the reviewed pilot contract in `2026-09-25-h3-a100-performance-pilot-plan.md`.

## One-session flow

The operator command, after separate paid-execution authorization, is:

```bash
python3 scripts/ops/colab_h3_a100_ab_host.py --max-cu 20
```

It requires the existing D: backup and dedicated rclone config. The command
creates one A100 high-memory Colab session, starts a deadline watchdog,
uploads only small control files, then performs the source/model restore **once**.
It installs the pinned Torch 2.14.0+cu130 environment and the already-built
SM80 wheel, verifies the frozen model/prompt/reference/parent/source hashes,
and runs `P_B -> P_C -> B1 -> C1 -> B2 -> C2` without restarting the VM.
`P_B/P_C` are one-step prewarms, not timing samples. Every formal sample
restarts only the ComfyUI process, thereby clearing node cache while keeping
the restored models and disk compilation cache. Baseline is `rtx4080(bypass)`;
candidate is the explicit `a100_sage_sm80` profile. The 5090 path is untouched.

Each run uses distinct MP4 and AV-latent prefixes. It saves the submitted
graph, ComfyUI history, full MP4/latent, finite AV-latent report, ffprobe and
audio-level checks, 12 sampler step elapsed times, timestamped external log
observations, five-second `nvidia-smi` telemetry, runner/Comfy logs, and a
phase receipt. Every phase is copied and checked on Drive before proceeding.
After stopping Colab, the host copies lightweight evidence to D:; MP4 and
safetensors stay on Drive. This avoids an unnecessary media download and
any repeat local-to-Drive model upload.

The B1/C1 timing screen requires at least 15% improvement in both server and
sampler time; otherwise the batch stops early and does **not** claim a pass.
The final screen also requires a second passing pair and baseline spread at
most 10%. Human audiovisual review and U03 continuation are separate gates;
the timing screen alone cannot authorize adoption.

## Cost admission and stop behavior

The historical A100 rate is 6.77 CU/hour. One cold restore was 14-15 minutes,
and a prior full bypass U02 took 26 minutes. Four such prompts plus restore,
two one-step prewarms, setup and backups suggest roughly 2-2.5 hours and
approximately 14-17 CU, **not a guarantee**. The script uses the live rate,
a 20 CU maximum inclusive of a 1 CU shutdown/backup reserve, and refuses any
full run that cannot fit its 40-minute maximum in both remaining CU and the
watchdog deadline. A full child prompt has a separate 35-minute timeout. A
failure, missing 12 steps, mismatched graph, invalid output or inadequate C1
gain stops the batch; it never auto-retries a full prompt.

The host `finally` stops the session and checks zero active assignments,
zero usage rate and no active sessions. The parallel watchdog also stops the
session at the absolute deadline. Do not invoke the operator command until
the 20 CU formal-stage ceiling is explicitly approved.

## Pre-execution verification boundary

- `python3 -m py_compile` passed for all new scripts.
- Repository test suite: 94 passed, 15 skipped. New contract tests cover
  attention-only graph normalization, actual tqdm reprint behavior, timing
  gates and CU admission.
- The saved historical bypass graph and diagnostic Sage graph normalize equal
  under the reviewed attention-edge/output-prefix whitelist.
- At preparation time, the actual GPU batch, media quality and stop path of
  this **new** driver had not been run. The subsequent runtime outcome,
  including a Colab CLI transport failure, is recorded in the results doc.
- Formal samples are not profiler-instrumented. The run log gate checks that
  the candidate patch is applied; the previous separate diagnostic proved 50
  SM80 extension calls, but no per-run CUDA kernel timing is asserted here.

Control scripts:
`scripts/ops/colab_h3_a100_ab_host.py`,
`scripts/ops/h3_a100_ab_preflight.py`,
`scripts/ops/h3_a100_ab_phase.py`,
`scripts/ops/h3_a100_ab_child.py`,
`scripts/ops/h3_a100_ab_contract.py`, and
`scripts/ops/colab_h3_paid_watchdog.sh`.
