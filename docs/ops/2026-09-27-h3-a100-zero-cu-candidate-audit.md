# H3 A100 zero-CU candidate audit (2026-09-27)

Status: offline audit only; Astra adversarial review passed. No Colab assignment, CU use,
new A100 runtime timing, image-quality test or production change in this pass.

## Frozen evidence checked

- Rental source archive SHA-256:
  `db6e20a71fe6ac87c7a4a981f08ae0685db7c0229d3db5bdd5b51f0832ab1fc7`.
  KJNodes `ltxv_nodes.py` member SHA-256:
  `11286583c56e653dbd57f5e8eda6902c84b759f16b359b3bf0c895b43e6b5364`;
  Sage SM80 `qk_int_sv_f16_cuda_sm80.cu` member SHA-256:
  `c4b64b76c32d517fe48788a25d578986d70f13a7b68f3ec550058f04b4d9214c`.
- Frozen KJNodes `minimax_sageattn_forward` projects the changing `x` to Q/K/V
  before each helper call. Its SM80 helper subtracts the K mean in place,
  quantizes Q/K per thread to INT8, casts V to FP16, then calls the
  FP32-accumulation SM80 attention kernel. Cross-step Q/K/V reuse is not valid.
- `mm.cast_to(self.q_norm.weight, device=device)` returns the same tensor when
  that weight is already on the requested device and no dtype conversion is
  requested. The same applies to `k_norm`. A cache of those already-resident
  weights would therefore not eliminate a copy. This is a conditional source
  result, **not** a measurement that weights always remained resident in U02.
- Sage dispatch fixes the current tile/quantizer-scale contract at
  `CTA_Q=128`, `CTA_K=64`, `WARP_Q=32`, `WARP_K=64`. Changing only a tile
  constant is not a valid one-variable candidate: scale shapes and padding
  are coupled to these values. The current 128-thread kernel uses 40,960 B
  dynamic shared memory for the profiled instantiation.

## What earlier tests do and do not say

The existing A100 same-instance Sage B/C pairs improved server wall by
15.43% and 15.55%. S1/M1 smart-memory changed full-U02 server wall from
1323.563 to 1321.416 s (0.16%), sampler from 1206 to 1206 s, while the
sampled VRAM peak rose from 35,910 to 51,396 MiB. The one-step P_C profile
reported 105.602 s wall, 50 Sage attention calls totaling 86.568 s aggregate
device time, 150 `comfy_kitchen::int8_linear` calls totaling 9.139 s, and
explicit HtoD events totaling 1.895 s. These profiler event totals are not
exclusive critical-path portions or additive estimates of server-wall saving.
The HtoD result does not exclude CPU/GPU synchronization or hidden stalls;
those need a stream-level timeline before an offload/prefetch claim.

The single offline `__launch_bounds__(128, 3)` rebuild lowered registers
255 to 168 per thread but raised stack 32 to 872 B and compiler-reported
spill stores/loads 32/40 to 2880/2768 B. Its predeclared static STOP gate
was triggered. Those are compile-time resources, not measured A100 traffic
or runtime slowdown. No output-equivalence test was done for that candidate.

The same-input 5090 U02 sample took 625.406 s server wall versus A100 C1
1324.348 s. This is a one-run deployment-combination comparison with a
different GPU-specific attention path, not a GPU-only benchmark or an A100
performance ceiling. The operator judged the two clips basically consistent;
full decoded audio/video acceptance remains separate.

## Decision boundary

This bounded source/resource pass found **no new specific, statically viable,
quality-preserving one-variable candidate** with a defensible route to a
material full-U02 wall reduction. It does not prove that A100 has no remaining
headroom. In particular, it does not approve speculative tile/warp sweeps,
weight-cache claims without measured nonresident copies, Q/K/V caching,
another smart-memory toggle, or a paid search-by-trial-and-error session.

Decision: `NO_CANDIDATE / NO_PAID_GATE` for this pass. Before requesting a
future paid A100 assignment, require a named candidate with a demonstrated
redundant operation or specific kernel-resource mechanism, a frozen one-variable
diff and rollback, complete-helper byte-equality plan on real pre-mutation
inputs, an interleaved timing gate, and a bounded full-U02 gate with CU/stop
budget. Any subsequent runtime result and its quality/performance claims must
go through Astra review before presentation as an accepted conclusion.

## Astra adversarial review

Astra independently read the archived KJNodes and `model_management.py` source
and accepted `NO_CANDIDATE / NO_PAID_GATE` **for this bounded pass only**.
The reviewer specifically rejected treating fixed weights as reusable Q/K/V,
counting the two `mm.cast_to` calls as two proven GPU copies, re-running the
failed launch-bounds candidate, or interpreting profile aggregate time as an
exclusive critical path. The reviewer also stressed that norm weights may be
nonresident at runtime, so the source-level no-op condition is not a claim
that U02 had zero copies. Static packing, local fusion, and kernel live-range
work remain research directions, not approved candidates.

Review clarification: a future compile candidate might reduce intermediate
memory traffic through a specific fusion even without launch gaps. It still
needs an identified source mechanism and equivalence plan before any CU
request. The 1.20x complete-helper / 10% server thresholds in the earlier
Phase B plan are project screening gates, not physical limits or a reason to
run a diagnostic session merely to reach a target number.
