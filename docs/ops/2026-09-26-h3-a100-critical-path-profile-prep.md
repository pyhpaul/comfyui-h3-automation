# A100 H3 one-step critical-path profile: offline preparation

Status: **prepared and locally tested, not run on a GPU**. No paid Colab
assignment, model transfer, inference result or new CU charge is claimed by
this document. The 2026-09-25 formal Sage A/B timing result and deferred
human quality gate remain separate.

Operator note: the user subsequently asked to minimize repeated Colab
startups. The combined conditional session is specified in
`2026-09-26-h3-a100-single-session-next-gate.md`. Do **not** launch this
profile-only driver as a separate paid session before deciding the combined
batch scope.

## Why this is next

The formal Sage U02 server wall was 1322-1324 s, including 1206-1208 s in
its 12 sampler steps: about 91% of server time. During steady sampling,
five-second `nvidia-smi` samples showed approximately 35.9 GiB VRAM and
near-100% utilization on an 80 GiB A100. This does **not** identify whether
H3 attention, quantized GEMM, H2D transfers, synchronization or another
kernel dominates. Model restore was paid once per VM, not per video. Changing
startup flags, weights or step count without a critical-path trace would be
another ungrounded A/B.

## Prepared instrumentation

- `scripts/ops/h3_a100_profile_hook.py` permits a temporary patch only when
  the archived `comfy_extras/nodes_custom_sampler.py` SHA-256 is exactly
  `b0ba1521c72475e06fed15db004274ed7c8bb2bf73f1d58849faf6f9f9d264fe`.
  It backs up the original file and records both hashes; restore refuses to
  overwrite an unexpectedly changed patch.
- `scripts/ops/h3_a100_profile_runtime.py` wraps the actual
  `SamplerCustomAdvanced` sample call with PyTorch CPU/CUDA profiling,
  CUDA synchronization, allocator peak capture and aggregate operator/kernel
  timings. It saves the 100 highest self-device-time entries and named
  transfer entries. It does not export a potentially enormous Chrome trace
  or claim the profiled wall time is comparable to formal B/C timings.
- `scripts/ops/h3_a100_profile_phase.py` runs one full-shape U02
  `motion_latent` Sage step after the frozen-input preflight, saves the
  profiler JSON, ComfyUI log, telemetry, submitted graph, history and finite
  AV latent, restores the source file, then copies/checks evidence on a
  unique Drive prefix. Its child has a 600 s limit; failure stops ComfyUI
  and still attempts evidence backup. No full U02 video is generated.
- `scripts/ops/colab_h3_a100_profile_host.py` is a separately authorized
  operator driver: one A100 high-memory assignment, one restore, same pinned
  Torch/SM80 wheel, frozen preflight, one diagnostic step, backup and stop.
  The preflight report is routed to this run's unique Drive prefix; the
  archived formal A/B evidence is not overwritten. Before assignment, it
  also checks that the local source archive contains the exact sampler file
  required by the profiler hook.
  It requires both `--execute-paid` and an explicit CU cap no greater than
  6. The watchdog and pre-step admission retain a 1 CU reserve. **Do not run
  it until the user separately approves this paid diagnostic.**

The operator command after authorization would be:

```bash
python3 scripts/ops/colab_h3_a100_profile_host.py --execute-paid --attended --max-cu 6
```

The Colab transport wrapper in `colab_h3_a100_ab_host.py` now applies host
timeouts to every CLI call, detects the observed `Connection was lost` error
without waiting for an inherited output pipe, and kills only its command
process group. On a phase transport failure it checks a timestamped Drive
receipt and current usage, writes `*.reconcile.json`, then stops **without
automatically retrying** an uncertain remote prompt. The independent paid
watchdog is terminated only after zero active assignments, zero rate and no
session are confirmed. This is a fail-closed improvement, not proof of
unattended Colab reliability; no live disconnect was rerun to validate it.

## Interpretation and next decision

This single-step profiler is intentionally diagnostic. If transfer events
are material on the step critical path, prepare a separate same-graph A/B
without `--disable-smart-memory`; consider a high-VRAM regime only after
allocator/device peak and safety-margin checks. If attention or GEMM/quantized
ops dominate, target that compute path or reassess hardware. Do not combine
memory flags with attention, model, reference, resolution or step-count
changes. A 4-step adapter could offer a larger theoretical gain but changes
the image/audio result and is deferred while human quality review is paused.

## Offline verification

- Focused A100 contract, profiler-hook, startup-flag and combined-driver
  tests: 27 passed. Tests cover bounded CLI
  transport/timeout, inherited-pipe regression, stale receipt rejection,
  watchdog retention, source-patch round trip and attention contract.
- All new/modified scripts passed `py_compile`. The patch was applied and
  compiled in memory against the archived ComfyUI source, with its exact
  49,739-byte source hash verified. The pinned Torch runtime and actual
  profiler event schema cannot be exercised in this local Python because
  `torch` is not installed; that remains a live diagnostic gate.
- System Python still lacks the declared `pytest_httpx` dev dependency. The
  full current-tree suite was later run through the existing
  `.worktrees/feat-orch/.venv`: 118 passed, 15 skipped. The skipped tests and
  live GPU path remain unverified. No unrelated user changes were reverted.
