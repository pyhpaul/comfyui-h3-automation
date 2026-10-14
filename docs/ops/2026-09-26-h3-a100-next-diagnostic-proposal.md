# A100 H3 next diagnostic and optimization gate (proposal)

Status: **Astra PASS for Gate 0 planning; offline Gate 0 implementation
recorded separately; Gate 1 not authorized**. The first
review was CONDITIONAL; the six required contract changes were incorporated
and a read-only re-review found no remaining Gate 0 blocker. This proposal
follows `2026-09-26-h3-a100-sm80-offline-audit.md`. It preserves the frozen
U02 workflow and separates diagnosis, speed research, and quality adoption.
Gate 0's code and offline tests are recorded in
`2026-09-26-h3-a100-gate0-implementation.md`. Review approval and offline
tests do not mean the instrumentation or shutdown path has run on Colab.
The subsequent Gate 1 contract review is **FAIL** pending offline trace
filtering, causal analysis and deadline fixes; see
`2026-09-26-h3-a100-gate1-run-contract.md` before requesting CU approval.

## Objective and invariants

Find a *specific* mechanism that can reduce the current A100 Sage U02
single-video wall time without lowering the accepted visual/audio quality.
The control is the archived S1 graph, six model files, U01 parent latent,
references, prompt, seed, 12 steps, resolution, LoRAs, quantization and
startup flags. Do not change any of these to manufacture a speed gain.
S1 is a performance control, not yet a user-accepted rental-5090 quality
reference. No change is adopted while that acceptance gap remains open.

## Gate 0: offline preparation, 0 CU

1. Verify the archived Sage source-tar, wheel and build-manifest hashes;
   inspect the actual FP32-accumulator SM80 branch and its quantizer contract.
   First try offline binary/compiler inspection for register and shared-memory
   requirements, including tools that do not require a GPU. A source-level
   estimate is not an occupancy or memory-bottleneck measurement.
2. Prepare an **opt-in, reversible** probe around the current attention call.
   Record real Q/K/V shapes, dtype, stride, device and attention head count.
   Use deferred CUDA events/timeline records with stream identity, **not** a
   full-device synchronization after each attention call. Bound event count,
   trace size, capture bytes, disk and peak-memory overhead. Capture a short
   timeline only if it can distinguish CPU launch gaps from GPU execution.
   A separate, clearly marked copy may save one full representative Q/K/V
   call **before the in-place K mean subtraction**, with any required scale
   tensors, only when the combined saved bytes fit 1 GiB and the extra
   VRAM/RAM limits pass. Do not count capture copy or serialization as an
   optimizable launch gap; verify restored tensor strides before reuse.
3. Fix the already observed terminal-receipt polling and raw-MP4 comparison
   problems before a new paid run. A receipt must bind a unique session/run,
   input manifest and attempt time, and be published only after required
   evidence is verified. Drive polling needs a short timeout and cannot
   block the independent deadline watcher. Compare normalized decoded media
   essence, not output-label bytes in the MP4 container.
4. Add tests for probe enable/disable, original-source hash guard, cleanup
   after failure, capture-size limits, bounded stage calls, receipt
   reconciliation and shutdown. Simulate CLI silence, stale/unreachable
   receipts, host transport loss and phase timeout. The current host `finally`
   and same-host watchdog cannot guarantee shutdown after complete host
  failure; either establish an independent stop path or require an attended
   run with an operator able to check and stop it manually (`--attended` is
   required by the prepared profile host). Do not describe
   the CU limit as an absolute billing guarantee. Ensure the uninstrumented
   graph and node settings remain unchanged.

The paid diagnostic is justified only if Gate 0 states a falsifiable question
and shows that the available tool can answer it:

| Observed signal | Decision it could change | Stop condition |
| --- | --- | --- |
| Unoverlapped launch gaps plausibly >=15% of one-step wall | Investigate graph-safe launch reduction without changing the graph's work | No reliable timeline or no material gaps |
| Quantization/conversion on the critical path with an identified redundant operation | Design a same-wrapper, same-output fusion candidate | Only aggregate operator totals or no concrete redundant work |
| Long SM80 attention kernel plus actual register/shared-memory or other limiting-resource evidence | Design one source-pinned kernel variant respecting the quantizer-scale shape contract | Kernel dominates but no resource-level mechanism is established |
| Copy/offload visibly stalls the critical path | Revisit a narrowly isolated transfer-policy candidate | Transfers overlap or the prior smart-memory null result remains unexplained |

The table does **not** claim these signals have been observed. If offline
inspection already resolves a branch or the proposed profiler cannot answer
its decisive question, do not allocate a GPU merely to collect more data.

Gate 0 exit: a reviewed instrumentation diff, local tests, fixed input
manifest, explicit branch question and dry-run of stop/accounting paths. If
these fail, report no paid candidate and stop.

## Gate 1: one bounded A100 diagnostic, separately authorized

Request an operator budget of **at most 6 CU**, inclusive of restore,
profiling, backup and shutdown, only after Gate 0 passes and the operator
separately approves the exact run contract. This is a watchdog/admission
limit, **not an absolute billing guarantee** under host failure. Before
allocation, use a conservative rate scenario, current balance and the stage
budget below to decide whether even attempting an assignment is reasonable.
The actual rate is known only after assignment; abort immediately if its
deadline cannot fit all remaining stages plus a 1 CU reserve. Use one
notebook-controlled A100 high-memory assignment, no public ComfyUI service.

| Stage | Maximum wall time after assignment |
| --- | ---: |
| upload controls, install, restore and SHA preflight | 22 min |
| one bounded profile step, optional capture, archive and receipt verification | 9 min |
| stop, usage/session reconciliation and margin | 4 min |
| **Total stage envelope** | **35 min** |

At the previously observed 6.77 CU/hour, `(6 - 1) / 6.77` gives about
44.3 minutes before the 1 CU reserve. That is only a planning example:
recompute with the actual assignment rate and reject any run with less than
35 minutes available. The prepared host enforces the 9-minute profile/archive
envelope as one stage; its internal profile and backup portions are not
separately hard-capped. Check elapsed time, projected stage CU, account
balance and the absolute deadline before every stage; a stage timeout means
stop, not use leftover balance to extend it. The existing host's independent
per-call timeouts are **not** proof that their sum fits this envelope.

Restore the same pinned models, source, wheel and parent latent once. Verify
SHA-256 and graph invariants before sampling. Run at most one instrumented
full-shape Sage step, plus a bounded representative Q/K/V capture only if
the size/memory gates pass. Instrumentation overhead is not a throughput
sample. Missing profiler support, exceeded trace size or insufficient stage
time is `inconclusive`, not a reason to run additional steps. Persist the
trace, shapes, timing, build/runtime identity, GPU telemetry and verified
receipt to Drive, then stop immediately. The host watches receipts while CLI
transport is silent and never blindly retries an uncertain prompt. An
unreachable receipt does not postpone the stop deadline. Verify zero active
assignments, zero usage rate and no active sessions after stopping; if the
host itself fails, manual/independent stop responsibility remains explicit.

Gate 1 exit: answer the predeclared branch question and classify measured
critical-path intervals, not just aggregate operator totals. Distinguish
launch gaps, attention CUDA execution, quantization, copy/offload and other
work; overlapping events must not be added. A CUDA timeline alone does not
identify occupancy or a register/memory bottleneck. If evidence is
inadequate, stop with `inconclusive` rather than tune by intuition. No full
U02 generation is part of this paid diagnostic.

## Gate 2: only if Gate 1 reveals a testable mechanism

Write a one-variable candidate contract: exact code/config change, why the
measured bottleneck should improve, expected speed bound, possible numeric
drift and rollback path. For example, a launch-overhead intervention requires
measured material launch gaps; a tile/warp variant requires resource evidence
and must preserve the quantizer-scale shape contract. `head_chunks=2`, more
VRAM, FP16 accumulation, fewer steps and smaller inputs are **not** default
candidates. Do not claim bitwise equivalence without a test.

First test the changed operation inside the *same complete wrapper* (Q/K
preprocessing, quantization, V conversion, attention, output conversion and
all allocations) against the archived Sage source, on representative real
tensors if captured. Metadata-only or random tensors may support a timing
hypothesis but **cannot** establish real-input correctness. First verify
that the unchanged control repeats stably and that the candidate wrapper
output tensor bytes equal the control. If bytes differ, report elementwise
and semantic drift and stop: no automatic full U02. Only a new, explicit
operator authorization may open a separate non-inferiority/human-review
branch for changed output.

For timing, use two unmeasured warm-ups of each wrapper, then five
interleaved control/candidate pairs with a reversed order on alternating
pairs. Synchronize at standalone microbenchmark boundaries, **not** after
every attention call inside full U02. Require control wall-time spread
`(max - min) / median <= 5%` and median
`control_wrapper_time / candidate_wrapper_time >= 1.20`. The wrapper time
includes all grouped calls, preprocessing, quantization, conversions and
allocation. These thresholds are stop rules, not predicted gains.

Only a byte-equal candidate passing that microbenchmark gate may request a
separately authorized, unprofiled, same-VM full U02 A/B. Use unique output
prefixes, process-cold runs with the same explicit cache/JIT prewarming,
and no skipped ComfyUI nodes. Run one control/candidate pair first; repeat
an interleaved pair only if the first meets the proposed >=10% server-wall
gain and artifact checks. Final timing acceptance requires both pairs to
clear >=10% against their **same-session** controls and control server-wall
spread <=10%; historical S1 is not the denominator. Record sampler and
server timing using the same boundaries, plus normalized decoded-media,
latent and graph hashes. Exact equality to A100 S1 only shows no *additional*
drift relative to S1; it does not establish parity with the original rental
5090 effect or replace the deferred blind human quality review.

Gate 2 gets its own CU estimate, cap and explicit operator approval after a
candidate exists. If no mechanism or no candidate passes, stop the A100
single-video optimization track and compare hardware or serving architecture
separately. Do not spend a second restore merely to repeat an inconclusive
probe.

## Decision record required after each gate

Report setup/restore/inference/backup/shutdown wall time and CU separately;
include GPU model, driver, Torch/CUDA, wheel/source hashes, clocks, peak VRAM,
trace coverage, prompt receipt, active-assignment check and output hashes.
Separate stage CU *estimates from rate and time* from actual account balance
delta; Colab does not supply an exact per-stage bill in this plan. Label
every claim as measured, inferred or unverified. Keep full media on Drive
and small evidence locally. The deferred Sage-versus-bypass human review and
same-input accepted rental-5090 reference remain separate quality gates.
