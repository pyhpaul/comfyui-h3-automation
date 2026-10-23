# A100 H3 next optimization plan for independent review

Status: Phase A offline audit and one-candidate build gate completed in
`2026-09-26-h3-a100-sm80-phase-a-result.md`. The candidate wheel was built
and rejected for substantial spill pressure. No Colab assignment or CU
authorization followed. The previous launch-gap Gate 1 remains disabled
(`PROFILE_GATE1_ENABLED=False`).

## Decision

Stop the current CPU-launch attribution probe and its 15% paid gate, not all
possible launch optimizations. The available PyTorch `FunctionEvent`
trace has no complete dependency-ready signal, so its qualified launch-gap
lower bound is always zero. Do not spend CU on a rule-out-only trace when the
goal is to find a quality-preserving speed candidate.

Prioritize the existing SM80 Sage attention kernel as an investigation target,
not as a proven bottleneck mechanism. In the archived one-step P_C profile,
50 attention kernel events account for 86.568 s of device time versus 105.602 s
profiled wall. Those are not additive critical-path intervals. The full U02
S1 server/sampler walls were 1323.563/1206 s. Smart-memory flag A/B was
effectively null; extra VRAM or head chunking has no demonstrated speed gain.

## Phase A: offline candidate discovery, 0 CU

Timebox this audit to four focused engineering hours and at most one candidate.
If time expires without a concrete mechanism, record `STOP` rather than
expanding the search.

1. Reconfirm the pinned source tar, wheel, build manifest, ComfyUI/KJNodes
   call path and immutable U02 input hashes. Extract the actual SM80 kernel
   launch geometry and quantizer-scale contract. Try local, non-GPU binary
   resource inspection; distinguish confirmed registers/shared memory from
   source estimates. Do not install a large toolkit merely for speculation.
2. Produce **one** narrow candidate only if a measured resource limit or
   demonstrably redundant operation and an
   output-preserving implementation route can be stated. Candidate scope is
   the same complete Sage helper (Q/K preprocessing, quantization, V cast,
   attention, output cast and allocations). No step/resolution/model/LoRA,
   quantization boundary, FP32 accumulation, prompt or reference changes.
   A compiler/build or launch-configuration change is not presumed numerically
   equal; it must pass a real-input byte comparison.
3. For `f > 0.10`, compute the wrapper speedup required for 10% server-wall
   gain as `1 / (1 - 0.10/f)`, where `f` is the *unknown* critical-path
   server-wall share of the affected wrapper. At `f = 0.10` infinite speedup
   would be needed; below that, this wrapper alone cannot reach 10%. For a
   1.20x helper speedup, `f` must be at
   least 0.60; the archived 86.568 s aggregate cannot establish `f`.
   Report pessimistic/optimistic `f`, the corresponding required speedups,
   what is measured versus assumed, and the unmeasured conditions. A high
   kernel aggregate alone is not `GO`. Without a specific mechanism and a
   defensible route to material server-wall savings, stop and compare
   hardware/serving economics separately.

Phase A exit artifact: source/build hashes, exact one-variable diff, observed
limitation/redundancy and why the candidate removes it, correctness risks,
conditional benefit interval, required wrapper speedup, rollback,
microbenchmark fixture design, and a reasoned `GO` or `STOP`. Missing resource
evidence or a speculative tile/warp tweak is `STOP`, not `GO`.

## Phase B: one staged A100 assignment only after a new review and approval

Phase B is **not execution-ready** until a separate, candidate-specific run
contract specifies actual CU cap, per-stage deadlines, archive/stop reserve,
capture or inline-comparison memory/time ceilings, two warm-ups plus five
interleaved microbenchmark pairs, and the number of full-U02 control/candidate
pairs. Admission before the final stage must cover the **whole required pair
set**, not only one run. Record evidence that receipt polling, independent
watchdog and the named attending operator's manual stop path work.

Preflight offline: source and input hashes, source patch restoration,
representative Q/K/V memory bound, Colab identity/rate/balance/session checks,
Drive capacity, upload/restore timing estimate, watchdog and manual stop.
Freeze a single CU cap and absolute stage deadlines **before** allocation;
the cap is an operational stop budget, not provider-enforced billing. If the
actual assignment rate cannot fit all planned stages plus reserve, stop.

Within one assignment, run the following sequence with no automatic replay:

1. Build and freeze both control and candidate implementations before the
   assignment. If a new wheel is required, prebuild and hash it; do not
   upgrade dependencies or compile an unpinned variant during the paid run.
   Where process-local switching is unsafe, use separate processes with the
   same frozen environment and explicit cache/JIT warm-up. Restore and verify
   that environment once. Capture actual Q/K/V
   shape/stride/dtype and a representative pre-mutation input only if the
   existing GPU/RAM/disk gates pass. If capture is impossible, use an inline
   real-input comparison or stop; random/metadata-only inputs cannot approve
   correctness.
2. On the **same complete helper**, compare control and candidate outputs on
   independent copies of the *same original, pre-mutation* real inputs;
   preserve stride/layout and never reuse tensors modified by the control's
   in-place K mean subtraction. Exclude capture/restoration work from the
   helper timing but include every candidate-added runtime operation. Require
   byte equality for the automatic quality-preserving
   path. If bytes differ, archive numeric/semantic differences and stop;
   only a separately approved human non-inferiority path may reconsider it.
3. If byte-equal, run interleaved control/candidate microbenchmarks with
   synchronized benchmark boundaries, not per-attention sync inside U02.
   Require stable control spread <=5% and median speedup >=1.20x. Account for
   preprocessing, quantization, casts, allocations and any new overhead.
4. A full-U02 A/B is a **separate stage within the same assignment only if
   pre-authorized in that session's contract**. First show repeated control
   runs are stable on the frozen graph and input. Require candidate complete
   latent tensor bytes, decoded video frames, PCM audio and frame/audio timing
   to equal the same-session control, alongside >=10% server-wall gain,
   telemetry and verified receipts. A hash is comparison evidence only when
   the decoded content and timing contract is explicit. Any mismatch or
   unstable control stops the automatic path, even if the helper matched.
   Otherwise stop after microbenchmark; do not keep the A100 idle awaiting a
   decision.

Any failed/unknown receipt, hash mismatch, resource gate, numerical gate,
timing gate, budget gate or stage deadline ends the assignment. Archive small
evidence within a fixed best-effort timeout, then stop even if Drive fails;
confirm zero active assignments, zero usage rate and
no active sessions. Human Sage-vs-bypass review and a same-input accepted
rental-5090 reference remain separate quality-adoption gates.

## Review questions for Astra

1. Does existing evidence justify kernel-focused offline candidate search,
   or is even this prioritization too weak without a critical-path trace?
2. Is a byte-equal full-helper candidate technically plausible while keeping
   the current FP32 accumulation and quantization contract? If not, what
   falsifiable zero-CU exit should replace Phase A?
3. Are the Phase B correctness/performance gates and one-assignment sequencing
   sufficient to avoid repeated restore cost and accidental quality tradeoff?
4. What exact evidence must be present before requesting any new CU budget?
