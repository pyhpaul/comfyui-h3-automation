# A100 H3 Gate 1: one-session diagnostic run contract

Status: **Astra FAIL; paid driver is disabled; do not request paid authorization**.
Gate 0's
offline code and tests are recorded in `2026-09-26-h3-a100-gate0-implementation.md`.
This gate diagnoses the existing Sage SM80 U02 sampler; it does not implement
an optimization, generate a complete U02 video, or accept visual quality.

## Offline repair after the FAIL review

- The exporter now keeps every `FunctionEvent` (not an arbitrary first 50,000),
  including correlation/flow, parent, activity, device/stream and timestamps,
  in a gzip JSON trace capped at 32 MiB compressed. Exceeding that limit
  produces `available=false`, not a purported complete trace. The limit is
  **post-collection** and does not bound PyTorch profiler memory; the prior
  successful one-step profiler is only feasibility evidence, not a guarantee.
- `h3_sampler_interval` encloses the call and final CUDA synchronization but
  excludes profiler-context exit. `h3_sage_wrapper` still encloses only the
  Sage helper, not complete attention forward. The interval analyzer unions
  GPU activity across streams, counts copies as device work, and treats queued
  kernels, CPU synchronization, dependencies and missing causal links as
  unknown. It never mistakes a GPU-idle interval for proven launch overhead.
- The pinned [PyTorch 2.14 FunctionEvent source](https://github.com/pytorch/pytorch/blob/v2.14.0/torch/autograd/profiler_util.py)
  and [Kineto conversion source](https://github.com/pytorch/pytorch/blob/v2.14.0/torch/autograd/profiler.py)
  expose the fields used by the exporter, but they do **not** supply a complete
  dependency-ready signal. Therefore the qualified-gap lower bound is always
  zero with this probe. A complete trace can only rule this branch out when
  the all-possible upper bound is below 15%; it cannot support the >=15%
  launch hypothesis. Runtime schema and clock behavior have not been checked
  on the target A100. Synthetic tests do not substitute for that check.
- Remote manifest retrieval, usage snapshots, receipt polling and failed-phase
  reconciliation now share the stage end. The profile remote CLI timeout is
  reduced to the 9-minute phase ceiling; at host stage expiry reconciliation
  skips network calls and the driver enters `finally` to stop the assignment.
  The independent watchdog and manual stop remain required for host failure.

**Decision:** do not spend CU on this probe. `PROFILE_GATE1_ENABLED=False`
enforces that decision even when paid flags are supplied. A new design must
capture dependency readiness or change the question to a rule-out-only bound,
then receive independent review and separate paid authorization. The code
below remains a historical run contract, not an executable approval.

## Astra review: paid-run blockers (resolve offline first)

The archived P_C `sampler-profile.json` has **79,926 calls in just its top
100 aggregate rows**. The original 50,000-event discard has been removed;
compressed complete export now fails closed at the byte ceiling. Collection
memory remains unbounded by this export cap.

Before re-review, implement and test an offline trace analyzer against a
verified pinned-Torch event schema. Preserve launch-to-kernel correlation,
parent/child relationships, stream identity, sync/dependency and copy events
where available. Tests must cover overlapping streams, queued-but-not-running
kernels, cross-stream dependencies, synchronous waits, copies, missing links
and trace truncation. If the PyTorch event schema cannot support causal
classification, redesign the probe or stop this branch without paid GPU use.

Define a sampler interval aligned with the trace, excluding profiler-context
exit overhead. The current marker covers only `_sageattn_int8_fp8_nhd`, not
QKV projection, RMS/RoPE or `out_proj`; call it the **Sage helper interval**,
not the complete attention forward. Report qualified-gap *lower bound* and
unknown-possible *upper bound*: lower bound >=15% supports further offline
design; upper bound <15% rules this specific launch-gap branch out; all
other cases are `inconclusive`. GPU idle or a CPU wrapper span alone does not
prove CPU launch overhead.

Finally, include remote manifest retrieval, usage snapshots and failed-phase
reconciliation in one absolute stage deadline; on a 540-second host phase
timeout, immediately stop the assignment rather than relying on the remote
1200-second timeout. Clarify that verified remote payload plus a host-validated
receipt is sufficient: the host may observe the terminal receipt before the
remote publisher's readback finishes. Keep an identified attending operator
and an independently usable manual stop path for total host failure.

**Review outcome:** no paid authorization should be requested until these
offline repairs pass tests and receive a brief independent re-review.

## Decision this spend must answer

The only primary question is whether **qualified, unoverlapped CPU launch
gaps attributable to the current Sage helper occupy at least 15% of one
full-shape U02 sampling step's wall time**. A qualified gap must have aligned
CPU/GPU timestamps, a helper marker, correlated launch/kernel evidence and
no competing stream/dependency/sync/copy explanation. Use the union of time
intervals, not a sum of overlapping profiler aggregates. If attribution is
ambiguous, count that interval as *unknown*, not as a launch gap.

The 15% threshold is a screening rule: with about 91% of the measured U02
server wall in the sampler, it leaves theoretical headroom for a later
10%-server-wall candidate, but does not predict that a graph/launch change
can remove those gaps. Secondary observations of quantization or copies may
be reported; they do not expand this paid gate into another A/B.

## Before allocation (0 CU)

1. Review the exact current files and frozen SHA manifest: source archive,
   Sage SM80 wheel, six models, U01 parent latent, U02 references/prompt,
   submitted graph, probe hooks and stage driver. Refuse unknown source or
   changed input. Confirm optional Q/K/V capture is **off**.
2. Implement and validate the trace-analysis procedure offline against
   pinned-schema fixtures and synthetic events:
   aligned CPU/GPU clocks, two streams, overlapping kernels, excluded
   `h3_probe_*` spans, missing resource IDs, and truncated trace. It must
   produce qualified-gap lower and unknown-possible upper bounds, not simply
   subtract summed kernel durations from wall time. If this cannot be done
   reliably, stop before allocation.
3. Check local script syntax/tests, Drive destination uniqueness and space,
   `colab usage`/`colab sessions`, and an attended manual-stop path. Require
   zero pre-existing assignments/sessions. Confirm the operator accepts one
   **up-to-6-CU** diagnostic budget. The prior 6.77 CU/hour rate is only a
   planning observation; use live assignment rate after allocation.

## Exactly one paid session, only after separate approval

Use `colab_h3_a100_profile_host.py` with explicit `--execute-paid --attended
--max-cu 6`. Request one A100 high-memory runtime; abort if it is not the
expected A100-SXM4-80GB/SM80, if live rate or balance fails admission, or if
the `(6 CU - 1 CU reserve) / actual rate` work window cannot cover the
remaining 35-minute envelope. This is a stop/watchdog budget, **not** a
provider-enforced hard billing cap if the host itself fails.

| Stage after assignment | Maximum wall time | Stop rule |
| --- | ---: | --- |
| controls, restore, setup and 13-input SHA preflight | 22 min | any hash, identity or stage timeout fails |
| one instrumented full-shape Sage step and verified Drive archive | 9 min | no replay on failed/uncertain receipt; no Q/K/V dump |
| stop, usage/session reconciliation and margin | 4 min | manual intervention if zero active/rate/sessions cannot be confirmed |

The new session runs one U02 `motion_latent` **one-step** graph with the
unchanged parent U01 latent, Sage SM80 profile and current model/reference
bytes. It records bounded wrapper markers and Q/K/V metadata, the sampler
profile and a complete gzip timeline capped at 32 MiB; full Q/K/V capture stays
disabled. No MP4, full 12-step U02, second profile or candidate benchmark is
included. A unique session/attempt/preflight hash binds each receipt. Publish
the terminal receipt only after remote evidence verification. Poll receipts
while CLI is silent; never blindly retry a prompt whose execution is
uncertain. Stop immediately after the verified receipt or any failure.

## Evidence, interpretation and exit

Persist preflight, runtime identity, both reversible patch manifests,
submitted graph/history, attention metadata, profiler summary/timeline,
ComfyUI/runner logs, five-second GPU telemetry, verified phase receipt,
stage wall times, CU balance/rate snapshots and session history. Keep the
small evidence copy on D: and verified source data on Drive. Check local
source restoration before releasing the runtime. Finally verify `0` active
assignments, `0.00 CU/hour`, and no active sessions; if the host or network
fails, the attending operator checks and stops the assignment manually.

Classify the result as exactly one of:

- **Actionable launch hypothesis:** timeline is complete and aligned;
  qualified gaps cover >=15% of the one-step wall and a concrete graph-safe,
  same-work launch intervention can be stated. This allows *offline design*
  of one candidate, not another paid run or quality adoption.
- **No launch candidate:** a valid trace places the unknown-possible upper
  bound below 15%. Stop this branch; do not retune tiles, precision, steps
  or model as a substitute.
- **Inconclusive:** unavailable/truncated timeline, missing stream/timestamp
  identity or causal links, qualified lower bound <15% while possible upper
  bound remains >=15%, capture/profiler distortion that cannot be excluded,
  missing receipts, or failed source restoration. Report the evidence gap
  and CU; do not automatically repeat the session.

No branch promotes a changed model output. Any later candidate must pass
the separate same-wrapper byte-equality and >=1.20x microbenchmark gates,
then obtain fresh CU authorization for same-session full-U02 A/B. The
deferred human Sage-versus-bypass review and accepted same-input rental 5090
quality reference remain independent prerequisites to claiming the original
effect is maintained.
