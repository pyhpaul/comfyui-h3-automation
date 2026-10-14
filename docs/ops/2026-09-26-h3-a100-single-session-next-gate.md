# A100 next gate: one restored session, conditional tests

Status: **run completed and stopped on the first-pair fail gate**. The operator
authorized a 20 CU maximum and the one-session driver ran on 2026-09-26.
Observed consumption was 10.09 CU; no assignment remains. See
`2026-09-26-h3-a100-combined-results.md` for measured results, artifacts and
the Colab CLI transport-loss finding. The sequence below is the frozen plan,
not a recommendation to rerun it.

## Evidence and target

The formal same-VM Sage A/B reduced fixed U02 server wall from about 1566 s
to 1322-1324 s. The Sage run still spends 1206-1208 s in 12 sampling steps
(about 91% of server time). Five-second telemetry observed near-100% GPU
utilization and about 35.9 GiB sampled peak VRAM, but cannot attribute the
critical path. The archived ComfyUI CLI says `--disable-smart-memory`
aggressively offloads models to RAM, while `--lowvram` can be inert with
dynamic VRAM. Those semantics do not prove per-step offload.

The goal of this session is to identify a **same-workflow**, runtime-only
speedup. No new checkpoint, reference size, resolution, LoRA, sampler step
count or prompt is in scope while human quality review is deferred. The
historical rental 5090 timing is not a controlled denominator.

## One-session sequence

1. **Admit and freeze:** one A100-SXM4-80GB assignment; live CU rate and a
   separately approved hard cap; host watchdog; one restore of six models and
   the same U01 parent latent; SHA preflight for source, wheel, models,
   prompt and references. Record driver/Torch/ComfyUI/GPU identity and clocks.
2. **Diagnostic only:** process-cold, full-shape, one-step profiling of both
   existing bypass (`P_B`) and Sage (`P_C`) modes. Preserve submitted graphs, CUDA/CPU
   operator and kernel summaries, named H2D/copy events, allocator peak,
   five-second GPU telemetry and logs. Profiling runs are not timing samples.
   If the profiler is unavailable or its event taxonomy is insufficient,
   record `inconclusive` and do not guess a bottleneck.
3. **Memory-policy safety diagnostic:** profile one Sage step with only
   `--disable-smart-memory` removed (`M0`). It must produce a finite latent,
   apply Sage, log the expected memory mode and stay at or below a predeclared
   70 GiB Torch allocator reserved peak. This is not a timing comparison.
   An aggregate profiler report alone cannot prove whether transfer was
   unoverlapped, so one full paired comparison is the causal performance
   check. Do not escalate to `--highvram` from a 35.9 GiB sampled peak.
4. **Full paired comparison:** run process-cold, disk-JIT-prewarmed,
   unprofiled U02 `S1 -> M1` in the same VM; continue to `S2 -> M2` only if
   the first pair meets the speed and exact-output gates. `S` is current Sage
   and `M` changes only the startup memory flag. Keep the
   fixed U02 graph, model bytes, parent latent, seed, 12 steps, references,
   output shape and format. Unique prefixes prevent ComfyUI cache and output
   overwrite. Record server/sampler/per-step time, telemetry, MP4 and AV
   latent checks, graph normalization and Drive backup after each prompt.
   Stop after the first pair if the candidate fails the predeclared
   benefit/output gate; do not spend a second pair to rescue it.
5. **Stop and account:** restore any temporary source hook, stop the VM,
   confirm zero active assignments/rate/sessions, export CU snapshots and
   lightweight evidence to D:. Keep full videos/latents on Drive. A CLI
   transport failure requires timestamped remote receipt reconciliation,
   never a blind retry.

The memory branch is not accepted from a one-step smoke. A pilot timing pass
requires both full pairs to improve server and sampler time by at least 15%,
baseline spread no greater than 10%, no unsafe memory peak, and valid media
and latent artifacts. Since quality review is paused, compare output SHA-256
with the current Sage control: byte-identical outputs can establish that the
memory-only change preserved these artifacts; any changed output remains a
human-review gate, not automatic acceptance. This does not resolve the
already-deferred Sage-versus-bypass quality gate or authorize U03.

## Budget and stop conditions

At the last observed 6.77 CU/h, one restore took about 19.6 min; each Sage
full U02 took about 22 min. Three diagnostic steps and four
unprofiled full runs, backups and shutdown plausibly need around 2-2.5 h,
or roughly 14-17 CU. This is a planning range, **not** a price guarantee.
A combined batch requests no more than a separately authorized 20 CU hard
cap inclusive of 1 CU reserve, re-admits each phase using the live rate,
and stops early if the first pair fails. The combined driver has bounded
Colab calls, per-phase Drive receipt reconciliation on transport failure,
unique output prefixes and full media/latent hash gates. The separate
`colab_h3_a100_profile_host.py` still only performs a single diagnostic and
has a 6 CU ceiling; it must not be mistaken for the combined batch.

Offline validation: 27 focused system-Python tests passed, including exact startup-argv
comparison showing that the two memory modes differ only by
`--disable-smart-memory`, graph normalization, first-pair fail-stop, second
pair drift rejection, CU admission, missing paid flag, CLI transport timeout
and watchdog retention. All scripts passed `py_compile`; the archived
ComfyUI profiler patch compiled with its frozen SHA. The full current-tree
suite in the existing `.worktrees/feat-orch/.venv` passed with 118 passed,
15 skipped; this is local verification, not GPU execution or quality
acceptance. The pinned Torch profiler and full combined run remain
unverified until authorized GPU use.
