# A100 H3 diagnostic Gate 0: offline implementation receipt

Status: **offline instrumentation scaffold tested; Gate 1 readiness blocked
by Astra's trace-analysis review; no Colab assignment or GPU test was started**.
The paid Gate 1 in
`2026-09-26-h3-a100-next-diagnostic-proposal.md` remains unauthorized. This
receipt is not evidence that the pinned Torch 2.14/CUDA profiler event schema,
Colab CLI or live receipt polling has been exercised on A100.

Post-review update: the 50,000-event export described below was replaced by
complete gzip export with a 32 MiB compressed limit, an aligned sampler
marker, conservative interval bounds and shared host stage deadlines. Offline
verification is now **142 passed, 15 skipped** (`uv run --extra dev pytest -q`).
The PyTorch event schema is confirmed from pinned upstream source, not live
A100 behavior. A nonzero causal launch-gap lower bound still cannot be
established from `FunctionEvent` alone, so the paid Gate 1 driver is disabled.
See `2026-09-26-h3-a100-gate1-run-contract.md` for the current decision;
the rest of this receipt records the earlier scaffold as it stood then.

## Prepared changes

- A hash-locked, reversible patch to the archived KJNodes H3 attention call
  marks wrapper intervals and records at most eight pre-mutation Q/K/V
  metadata sets. Optional one-call
  real Q/K/V capture defaults **off**; it checks a combined 1 GiB tensor
  limit, GPU headroom, cgroup-aware RAM and disk before copying. Capture
  operations are marked as excluded from launch-gap interpretation.
- The existing one-step sampler profiler can export a bounded CPU/CUDA event
  timeline with device/resource identifiers: at most 50,000 events and
  32 MiB serialized. Unsupported schema or a size-limit hit is reported as
  unavailable, not silently treated as a valid critical-path trace.
- Remote phase receipts now include unique session, attempt and preflight
  manifest identity. Payload is copied and checked before `phase.json` is
  published; the receipt is read back. During a silent `colab exec`, the
  host polls with a five-second Drive read timeout, stops on a verified
  terminal receipt and never retries an uncertain phase. A missing receipt
  does not delay the independent same-host deadline watcher. Complete host
  failure still needs an attending operator; the profile driver now requires
  `--attended` as well as `--execute-paid` and `--max-cu`.
- MP4 comparison uses SHA-256 of decoded video and audio streams, while
  retaining the raw container hash for provenance. A fixture with identical
  encoded streams and different MP4 metadata passes the decoded comparison.
- The profile driver enforces an offline-prepared 35-minute stage envelope
  after assignment: 22 minutes for setup/restore/preflight, nine minutes for
  profile plus verified archive, four minutes for stop/margin. It checks the
  actual assignment rate and a 1 CU reserve before proceeding. A 6 CU input
  is an operational watchdog/admission budget, **not a guaranteed charge cap
  under host failure**. Stage timeouts stop the session rather than extending
  it from remaining account balance.

## Falsifiable Gate 1 question

If separately authorized, the single diagnostic asks whether **unoverlapped
CPU launch gaps attributable to the current H3 wrapper plausibly account for
at least 15% of the full-shape one-step wall time** after excluding probe
capture/logging intervals. The existing aggregate Sage kernel time alone
cannot answer that. If the bounded timeline lacks aligned CPU/GPU timestamps
and resource IDs, exceeds its limits, or shows no material launch-gap headroom,
the answer is `inconclusive` or `no candidate`; do not run a full U02 A/B.
The same trace may motivate a quantization hypothesis only if it identifies
a concrete redundant operation on the critical path. A long attention kernel
without resource-level evidence is **not** permission to change tile/warp
settings or FP32 accumulation.

Offline binary inspection found the archived SM80 wheel and source hash, but
no local `cuobjdump`/`nvdisasm` and no captured `ptxas` register/shared-memory
report. Runtime occupancy and the pinned Torch profiler's live event schema
remain unverified. The attention patch was compiled in memory against the
archived KJNodes source with exact SHA-256
`11286583c56e653dbd57f5e8eda6902c84b759f16b359b3bf0c895b43e6b5364`.

## Offline verification

- Full current-tree suite in `.worktrees/feat-orch/.venv`:
  **135 passed, 15 skipped**. New tests cover patch round trip and source
  mismatch, bounded metadata/timeline, capture limits, receipt identity,
  publication ordering, silent CLI termination, unreachable receipts,
  attended flag, stop verification and a simulated phase failure with host
  cleanup. The skipped integration tests are not a live GPU validation.
- Modified/new Python scripts passed `py_compile`; `git diff --check` and a
  trailing-whitespace scan passed. The decoded-content helper was tested
  with a real local `ffmpeg` synthetic MP4/remux fixture.

Next action is **not** to launch A100. Astra found that the historical P_C
top-100 aggregate rows already total 79,926 calls, above the current 50,000
raw-event export limit; the current trace also lacks a tested causal analyzer.
Complete the offline blockers in `2026-09-26-h3-a100-gate1-run-contract.md`
and obtain a brief re-review before requesting separate Gate 1 CU
authorization. A diagnostic pass would not authorize a speed candidate,
complete U02 A/B or quality adoption.
