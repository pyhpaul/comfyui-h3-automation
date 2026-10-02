# A100 H3 SM80 Phase A: offline resource finding and candidate gate

Status: **STOP at the offline build gate**. The only candidate compiled, but
its target kernel has substantial new spill pressure. Paid Phase B is not
ready or authorized. No Colab assignment or GPU run occurred in this phase.

## Evidence fixed to the archived run

- Rechecked SHA-256: `source-only.tar`
  `db6e20a71fe6ac87c7a4a981f08ae0685db7c0229d3db5bdd5b51f0832ab1fc7`,
  Sage source tar `42651d8da657de9cae5ca291012cf0d4f3aec9e9f878f15cb8b7cfa4b59aaad6`,
  SM80 wheel `36fb6b6febdcd71aa171fa207291b40696a5f4384451100348a1ebdfec8a8238`.
  The archived P_C preflight reports 13/13 matching assets and a matching
  U01 parent. This is an archived runtime receipt, not a fresh read of all
  model bytes today.
- Frozen S1 graph node 58 is `MiniMaxH3MemoryEfficientSageAttentionPatch`.
  KJNodes calls `_qattn_sm80.qk_int8_sv_f16_accum_f32_attn` after in-place K
  mean subtraction, per-thread INT8 Q/K quantization and V-to-FP16 cast.
  The archived profile identifies the exact FP32-accumulator, BF16-output,
  noncausal, no-LSE SM80 instantiation: 50 events and 86.568 s aggregate
  device time in a 105.602 s **profiled one-step wall**. Aggregate device
  time is not a mutually exclusive critical-path share.
- Source launch geometry is `CTA_Q=128`, `CTA_K=64`, `WARP_Q=32`,
  `WARP_K=64`, `HEAD_DIM=128`, `block=(32,4)` = 128 threads. Source computes
  40,960 bytes dynamic shared memory per block for this instantiation.
- Official CUDA 13.0 `cuobjdump -res-usage` on the **archived wheel**, matched
  to that exact mangled kernel, reports `REG:255 STACK:32 SHARED:0 LOCAL:0`.
  `SHARED:0` is static allocation; it does not negate the 40,960-byte dynamic
  launch argument. Its SASS contains six `STL` and eight `LDL` instructions;
  these are static instructions, not measured local-memory traffic or proof
  that spilling dominates wall time. The full resource listing and selected
  SASS are preserved at
  `/mnt/d/comfyui-h3-backups/rental-20260924-5090/a100-perf-pilot/offline-sm80-20260926/`.

[NVIDIA's Ampere guide](https://docs.nvidia.com/cuda/ampere-tuning-guide/)
specifies 64K 32-bit registers, 64 resident warps and 164 KiB shared memory
per A100 SM. Thus 255 registers x 128 threads, after allocation rounding,
limit this kernel to **at most two blocks / eight warps per SM** by register
capacity; 40 KiB dynamic shared memory alone could fit three blocks. This is
a *static eligibility ceiling*, not an observed occupancy, utilization,
latency cause, or speedup prediction. Runtime shared-memory carveout and
register-allocation granularity still need verification.

## Exactly one candidate hypothesis

`patches/h3-sage-sm80-launch-bounds-128x3.patch` adds
`__launch_bounds__(128, 3)` to the SM80 attention kernel template. The patch
passes `git apply --check` against the hash-pinned source tar. It changes no
model bytes, quantizer scale layout, accumulation dtype, kernel arithmetic
source, sampler steps, graph, prompt or references. It does change compiler
resource allocation for **all** instantiations of this template; byte
equality is not assumed.

The compiler hint asks for three resident blocks, which would require about
168 or fewer registers per thread after allocation granularity. With 40 KiB
dynamic shared memory, three blocks also require a compatible >=120 KiB
shared-memory carveout. If both conditions hold, the eligibility ceiling
could rise from eight to 12 warps/SM. A lower register budget may create
additional spills and make the kernel slower; higher occupancy is not a
performance result. [CUDA launch-bounds documentation](https://docs.nvidia.com/cuda/cuda-programming-guide/05-appendices/cpp-language-extensions.html)
explicitly treats register use, spilling and instruction count as a tradeoff.

## Zero-CU gate before any A100 request

1. Build a candidate wheel with the **same pinned** CPython 3.13, Torch
   2.14.0+cu130, CUDA 13.0 and source as the control, changing only the patch.
   Freeze source, build log, toolchain and wheel hashes. This was completed
   using an isolated local builder; see the result below.
2. Run `cuobjdump -res-usage` and targeted SASS comparison on both wheels.
   If the target still cannot support three blocks, or if register reduction
   causes substantial new `STACK`/`LOCAL` or `LDL`/`STL` pressure without an
   independently defensible benefit, record `STOP` before spending CU. Also
   confirm the changed wheel remains SM80-only and that its other kernels are
   not being silently used in the frozen U02 path.
3. Only a frozen, statically viable wheel may be proposed for the separate
   candidate-specific Phase B contract. On A100, first query actual block
   residency with the CUDA occupancy API and compare independent copies of
   the same real, pre-mutation Q/K/V at the **complete Sage helper** boundary.
   Byte inequality, spill-driven slowdown or inability to establish the
   required shared-memory carveout ends the run. No full U02 is automatic.

Let `f` be the as-yet-unmeasured *critical-path server-wall share* affected
by this helper. A 1.20x helper gain gives `f/6` server-wall gain: 5% at
`f=0.30`, 10% at `f=0.60`, 12.5% at `f=0.75`. The 86.568 s profiler aggregate
does **not** establish `f`. The earlier decision was GO only to a bounded
offline build/resource check, NO-GO to paid GPU. That check is now complete
and rejected this candidate; do not substitute speculative tile/precision
changes under this one-candidate plan.

For a 10% server-wall gain, the required complete-helper speedup is
`1 / (1 - 0.10/f)`: 1.50x if `f=0.30`, 1.20x if `f=0.60`, and about 1.154x
if `f=0.75`. These are conditional examples, not estimates of this patch.
The rollback is the hash-pinned unpatched source and control wheel above;
neither the frozen workflow nor its model/input artifacts should be edited.
If Phase B is separately approved, its microbenchmark fixture must capture
the actual helper-entry Q/K/V shapes, dtypes, strides and pre-mutation bytes
from frozen U02, then run independent copies through the **whole helper**.
The contract in `2026-09-26-h3-a100-next-plan-for-astra.md` requires two
warm-ups and five interleaved pairs, including preprocessing and allocations
in timing. No random-input microbenchmark can approve correctness or quality.

## Offline build result: STOP

The archived binary has no PTX, so a matching source rebuild was necessary.
The host's glibc 2.43 headers conflict with CUDA 13.0 `rsqrt` declarations;
both wheels were instead built in the same isolated Ubuntu 24.04 container
(glibc 2.39, GCC 13.3). The builder used CPython 3.13.13 rather than the
archived 3.13.15 patch level, but kept the same CPython ABI, Torch
2.14.0+cu130, CUDA 13.0 `nvcc`/`ptxas` 13.0.88 and pinned Sage source.
Rebuilt control and candidate must be compared to each other, not assumed
byte-identical to the archived wheel. The rebuilt control reproduces the
archived target resource result `REG:255 STACK:32`.

| Exact U02 kernel, static compile result | Rebuilt control | Candidate |
| --- | ---: | ---: |
| Registers/thread | 255 | 168 |
| Stack frame/thread | 32 B | 872 B |
| `ptxas` spill stores | 32 B | 2880 B |
| `ptxas` spill loads | 40 B | 2768 B |
| SASS `STL` instructions | 6 | 555 |
| SASS `LDL` instructions | 8 | 664 |

The spill values and instruction counts are **compile-time/static**, not
measured runtime traffic. Nevertheless, the candidate's 840 B larger stack
frame and roughly 90x/69x spill-store/load reports trigger the predeclared
STOP condition. A possible three-block residency ceiling does not justify
spending CU when the resource tradeoff is this severe and there is no
independent evidence of complete-helper speedup. No output equality,
microbenchmark, full-U02 timing or quality result is claimed. The local
GTX 1660 SUPER is SM75 and cannot execute this SM80-only wheel for the
required A100 comparison.

The exact copied artifacts are under
`/mnt/d/comfyui-h3-backups/rental-20260924-5090/a100-perf-pilot/offline-sm80-20260926/build-gate/`.
`SHA256SUMS` passed for both wheels, build logs, resource listings, target
SASS, package list, source and Dockerfile. Rebuilt control wheel SHA-256 is
`8e76a1e4e66d876e2d1b12781fd3add09d58a2dbf40631ec40b0b474fdcfa8f6`;
candidate wheel is
`73c0a7fc4c4b0cc4e49736f842691583389971a2a7d6d93faa7aa545fb5e2ac6`.
The candidate source has the intended launch-bounds line plus a final
newline added by patch application; this extra newline does not affect
compilation, but means its source bytes are not exactly the standalone patch
applied to the newline-less archived file.
The D-drive evidence bundle is about 20 MiB. The isolated local `uv` cache
uses about 9.6 GiB and is retained for now to avoid another dependency
download; it is not part of the deployment or Drive/model backup.

## Reproduction notes

The resource inspection used NVIDIA's `cuda-cuobjdump-13-0_13.0.85-1` and
`cuda-nvdisasm-13-0_13.0.85-1` packages extracted in `/tmp`, without system
installation. Package SHA-256: `c175036d8f87d624ebf073e2957bef640c968a05d8bd296eddd05818643e2d95`
and `a0edae45d1debe83291254405afa1ee95a1f653e1fc59ea2cc6ffff6f49eefb5`.
The copied resource listing hashes to
`d690b7fe31632f6095595d79443da478d49aafc202effab7d9ce37f0bcbe65c5`;
selected SASS hashes to
`bc4991b45665de5c5d3452b3984385f695105bf4680e7a7aec81b86f76801a1d`.
The package index and tool use are documented by
[NVIDIA's CUDA binary utilities guide](https://docs.nvidia.com/cuda/cuda-binary-utilities/).
