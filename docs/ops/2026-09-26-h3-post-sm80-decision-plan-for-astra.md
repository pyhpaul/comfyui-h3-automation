# H3 single-video latency after the SM80 STOP: decision plan for Astra

Status: **Astra PASS for the zero-CU Gate 0 decision preparation and
conditional route only**. The initial review was CONDITIONAL; its five
blocking corrections were incorporated and the read-only re-review found no
remaining blocker. No GPU allocation, rental restart, Colab CU, model
transfer, workflow modification or quality adoption is authorized by this
plan.

## Decision to make

Stop the current A100 single-video kernel-tuning branch. Its one allowed
`__launch_bounds__(128, 3)` candidate compiled with target `REG:168`, but
also raised the stack frame from 32 B to 872 B and `ptxas` spill
stores/loads from 32/40 B to 2880/2768 B. This is a predeclared static
STOP, not a measured runtime slowdown. Do not use that wheel in Colab or
search a second tile/precision candidate under the same budget.

The next decision is **whether this same-effect, single-video workload
belongs on A100 at all**, rather than how to force an unproven A100 patch.
The A100 Sage U02 has a measured 1322-1324 s server wall and 1206-1208 s
sampler wall in two frozen formal runs. A100 smart-memory removal gave
only 0.16% server and 0% sampler improvement in one full U02 pair; sampled
VRAM rose instead. The historical rental 5090 observation of 646-656 s was
client polling, not a byte-matched server-side comparison. It is directional
only. The same-effect requirement also remains unaccepted: the blinded
human Sage-versus-bypass review and an accepted same-input rental-5090
reference are deferred.

## Gate 0: zero-CU decision preparation

1. First inventory **existing** rental-5090 history, submitted graphs,
   source/model/input hashes, parent latent and server logs. If an existing
   same-input, fully timed U02 sample is already available, analyze it
   without scheduling another run. Historical client polling alone is not
   enough to rule out a preserved server-side record. Do not inspect or
   disclose the blind-review mapping. Then freeze the existing A100
   S1/C1/C2 evidence and 13-input manifest, the submitted U02 graph,
   U01 parent latent, six model hashes, prompt,
   references, seed, 12-step scheduler, resolution, LoRAs, output contract,
   startup flags and Sage wheel. Keep the original 5090 workflow/profile
   as the production control; do not install the rejected SM80 wheel there.
2. Prepare an **offline read-only comparison specification**, not the
   mutable `run_ep_units_profiled.py` path: compare preserved submitted
   graphs, or prepare the expected rental-5090 graph from the frozen U02
   input without submitting it. Assert an explicit diff allowlist for the
   architecture-specific attention backend and output prefixes. Abort if
   model, input, sampler or any other graph setting differs. Record the
   actual extension/source identities outside the graph. SM80 and SM120
   binaries cannot be byte-identical; this compares deployed workflows on
   matched inputs, not intrinsic GPU hardware in isolation. The eventual
   submission is a paid, output-writing operation, not a read-only check.
3. Define one receipt format for both environments: GPU/driver/clocks,
   Python/Torch/CUDA/Sage identity, source/model/input hashes, graph diff,
   process-cold/warm state, server/sampler/each-step wall, 5-second GPU
   utilization/VRAM, restore/setup/backup wall, and MP4/latent validation.
   Compare decoded video frames and PCM audio **and** frame/audio count,
   cadence, timestamps and time bases; raw MP4 labels are not semantic
   differences, but timing shifts are. Keep full media in its existing
   remote store; copy only small receipts to D unless delivery requires
   otherwise.
4. Before any future Colab allocation, verify that the **already implemented**
   silent-CLI terminal-receipt polling and decoded-stream hashing actually
   cover that run path, pass tests and work in the target environment. Add
   the missing media-timeline contract rather than reimplementing hashing.
   The prior silent wait consumed billed time. These are operational checks,
   not sampler speedups, and should not be bundled into a performance A/B.

Gate 0 exit: existing-artifact inventory, frozen manifest, graph-diff
allowlist, fixture-tested receipts and a reviewed command/runbook. If an
existing sample answers the screen, stop without another run. If the rental
image cannot prove matching model/input bytes or the graph diff cannot be
constrained, record `INCOMPARABLE` and do not run a nominal benchmark.

## Gate 1: at most one 5090 screening sample, no new A100 run

Use the **next already needed rental-5090 window** only if the frozen U02
input is already a planned job there. Otherwise one extra U02 is a new paid
task and requires an explicit cost/time authorization; this proposal does
not grant it. Do not restart a rental machine just to collect a number.

On admission, verify actual RTX 5090 identity, the original production
startup/configuration, and where all six models, source, parent latent and
reference files physically reside. Recheck their SHA-256, disk lifecycle
and enough free space. Time and account for even a small missing-input
transfer; if large model restoration is needed, stop for new approval rather
than assuming the rental image persists. Run one complete 12-step
`motion_latent` U02 using the production 5090 attention profile. Capture server-side timing,
not only client polling. Preserve the generated MP4 and AV latent with
media/finite checks. Change no steps, resolution, quantization, model,
LoRA, prompt or reference to make 5090 look faster. Do not reveal the
existing blind-review mapping.

Record process age, model load, JIT/warm-up and cache state in both the 5090
sample and the archived A100 receipts. Prove the sampler really executed
all 12 steps with a new prompt/history, sampler execution/progress logs and
new output evidence; a completion receipt or distinct filename alone is not
enough to exclude node-cache reuse. Do **not** restart the production
ComfyUI merely to clear caches. If cache state or concurrent production
loads cannot be controlled/explained, keep this as an actual-deployment
observation, not a credible acceleration multiplier.

This is a **screen**, not a final benchmark: A100 formal runs were stable,
but one new 5090 run has no same-session variance estimate. A large gap can
prioritize further evaluation of a deployment path; a small/ambiguous gap
cannot establish parity.
Do not automatically repeat the rental run. If a second sample is needed to
change a concrete acquisition decision, budget and authorize it separately.

## Gate 2: separate latency, economics and quality decisions

- Compare generation latency as server and sampler wall. Report the A100
  1322-1324 s formal range beside the new 5090 result with dates, different
  sessions and implementation-specific attention identified. Do not mix
  restore/setup into per-video generation time or call historical client
  polling an equivalent baseline.
- Report session economics separately: observed rental hourly price and
  Colab CU rate/balance at the time of use, restore/setup/backup cost, and
  amortized cost for one versus several consecutive units. Verify rental
  disk lifecycle after release/reassignment, storage fees and idle fees;
  an existing image does not guarantee persistent model bytes. The observed
  6.77 CU/hour A100 rate is historical, not a future price or guarantee.
- Keep quality acceptance independent. The existing blind human review must
  assess continuous video **and** audio before accepting Sage; the new
  same-input 5090 output needs an accepted reference check for identity,
  continuity, motion, dialogue/lip sync and artifacts. Until then, label
  any speed/cost comparison `performance screen only`, not same-effect
  deployment parity.
- If the matched 5090 deployment is materially faster and its quality is
  accepted, propose a **separate** Blackwell deployment/cost plan; this
  screen does not authorize ongoing rental, migration, or claim reliability
  of a complete U01-U03 chain. Retain Colab A100 only as a technically
  runnable portability/fallback option; concurrent throughput is unmeasured.
  If costs, inputs or quality are incomparable, decide nothing from the
  historical 646-656 s figure. If A100 remains a hard deployment constraint,
  request a **new** mechanism-specific plan and independent review; do not
  turn the rejected `launch_bounds`, smart-memory toggle, CUDA Graphs,
  fewer steps or lower resolution into an automatic follow-up.

Mark a performance comparison `INCOMPARABLE` when matching model/input/parent
or sampler settings cannot be proved; the actual attention binary/source
is unknown; sampler cache reuse, incomplete steps, unclear timing boundaries
or unbounded concurrent load prevents attribution. Different driver/Torch or
architecture-specific attention versions are not automatically invalid,
but must be disclosed as a **deployment-combination** comparison. Missing
human media review does not erase a valid timing observation, but prevents
the label `same effect` or an adoption decision.

NVIDIA documents CUDA Graphs primarily as a way to amortize repeated CPU
launch work; no qualified launch-gap lower bound exists for this workflow,
so enabling them is not the next candidate
([CUDA Graphs](https://docs.nvidia.com/cuda/cuda-programming-guide/04-special-topics/cuda-graphs.html)).
If a future A100-specific diagnosis becomes decision-critical, an Nsight
Systems CUDA API/GPU-stream timeline could answer execution-order questions;
Nsight Compute occupancy/local-memory metrics answer a different kernel
resource question and may require replay/permissions. Neither tool is an
authorization to start another A100 session
([Nsight Systems](https://docs.nvidia.com/nsight-systems/UserGuide/),
[Nsight Compute](https://docs.nvidia.com/nsight-compute/ProfilingGuide/),
[counter permissions](https://developer.nvidia.com/nvidia-development-tools-solutions-err_nvgpuctrperm-permission-issue-performance-counters)).

## Astra review questions

1. Does the offline spill result justify stopping this *candidate* without
   overclaiming that A100 has no remaining optimization headroom?
2. Is a next-window, one-sample matched-input 5090 screen preferable to a
   standalone A100 profile for the user's same-effect/single-video goal?
3. Are the diff/hash, timing, cost and human-quality boundaries sufficient
   to prevent a misleading 5090-versus-A100 conclusion? What exact missing
   evidence should make Gate 1 `INCOMPARABLE`?
4. Does any zero-CU alternative provide a more decision-useful next step
   without silently changing the workflow or restarting a paid instance?

## Review outcome

Astra accepted the final ordering: inspect existing 5090 evidence first;
if insufficient, prepare a matched-input screen for an already needed rental
window, with a separate approval for any additional generated sample or
large transfer. A valid single sample remains a performance screen, not
same-effect adoption, a persistent-rental decision, or proof that A100 has
no remaining optimization headroom. The review was read-only and started no
GPU session.
