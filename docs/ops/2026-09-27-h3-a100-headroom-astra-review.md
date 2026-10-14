# H3 A100 latency headroom: Astra adversarial review (2026-09-27)

Status: **offline review only; no new GPU run or approved candidate**.

## Corrected conclusion

Astra rejected the absolute claims that 80 GiB VRAM is useless, that A100 has
no remaining optimization headroom, or that replacing it with RTX 5090 is the
only possible route. The defensible result is narrower: Sage SM80 is a proven
~15.5% A100 server-wall improvement; one smart-memory flag A/B showed no
useful gain; one `launch_bounds` candidate failed its static spill gate; no
other quality-preserving A100 candidate has yet passed a causal performance
test. The same-input RTX 5090 sample is 52.8% shorter server wall, but it is
a one-run deployment-combination screen, not an A100 optimization ceiling.

## Evidence and interpretation

| Evidence | Result | Does not establish |
| --- | --- | --- |
| A100 B1/C1 and B2/C2 | Sage SM80 server -15.43% / -15.55%; sampler -16.63% / -16.71% | Every future run or alternative backend has the same gain |
| A100 S1/M1 | Smart-memory flag change: 1323.563 -> 1321.416 s server; 1206 -> 1206 s sampler; sampled VRAM peak 35910 -> 51396 MiB | Every residency, offload or prefetch strategy fails |
| A100 P_C one-step profiler | 105.602 s wall; Sage attention kernel 86.568 s aggregate device time; `comfy_kitchen::int8_linear` 9.139 s aggregate; named transfer/copy/conversion events 2.693 s, of which explicit HtoD is 1.895 s | Exclusive critical-path shares or a hard Amdahl bound; wrapper and child kernel totals must not be added |
| SM80 `launch_bounds(128,3)` offline build | Registers 255 -> 168, but stack 32 -> 872 B and static spill stores/loads 32/40 -> 2880/2768 B; predeclared STOP | Every occupancy or SM80 kernel rewrite is slow |
| Same-input 5090 U02 | 625.406 s versus A100 C1 1324.348 s, -52.8%; operator reports this pair basically consistent | GPU-only causation, run-to-run variance, full AV acceptance or exact economics |

The A100 sampler occupies about 91% of its server wall. The existing profiler
identifies attention as a high-priority investigation target but has no
stream-level critical-path timeline. If a candidate affects wall share `f`
and accelerates that share by `s`, the idealized total saving is
`f * (1 - 1/s)` before new overhead. Matching the observed 5090 wall would
require 52.8% total saving; even for an affected `f=0.8`, that implies about
2.94x local acceleration. This is a scale check, not an attainable forecast.

## Ranked, still-unproven mechanisms

1. **SM80 attention register lifetime and scheduling:** inspect the frozen
   source, live-value lifetime, generated SASS and resource usage for a
   specific spill-free change. Do not reuse the failed forced-occupancy patch.
2. **Cross-step invariant packing or weight/scale preparation:** trace which
   values are truly static and already cached. Do not cache changing Q/K/V or
   alter the quantization boundary without a quality gate.
3. **Offload/prefetch:** investigate only if a real GPU-stream/CPU timeline
   shows waits on the critical path that the tested smart-memory flag did not
   address. Unused VRAM alone is not proof of such a wait.
4. **INT8 linear and surrounding conversion/fusion:** inspect repeated casts,
   layouts and packing using the 9.139 s aggregate clue; avoid counting an
   operator and its child CUTLASS kernel twice. CUDA Graph or compilation
   changes require measured launch gaps/graph-break overhead first.

## Next gate, without wasting CU

First perform a bounded zero-CU source/SASS audit and nominate at most one
specific, quality-preserving mechanism. If no concrete redundant work or
resource fix is found, stop; do not open Colab to search by trial and error.
For a future paid test, freeze the control and candidate source/wheels,
capture real helper inputs, compare the complete helper including added
preprocessing/allocations, establish stable interleaved control timings, and
estimate whether the measured local gain could yield at least 10% full-U02
server-wall gain. Only then request a bounded same-session full-graph A/B with
unchanged model, prompt, parent, references, seed, 12 steps and resolution,
plus decoded media/timeline and operator quality checks. Restore, compile,
backup and stop time must fit the authorized CU window.

No lower steps/resolution, model/LoRA swap, precision change advertised as
automatically equivalent, another smart-memory flag retest, blind high-VRAM
toggle, or uncontrolled kernel tile search belongs in that gate.
