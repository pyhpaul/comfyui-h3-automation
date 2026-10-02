# A100 H3 SM80 offline optimization audit

Status: **read-only audit complete; no Colab runtime started and no CU spent**.
This follows the three-round adversarial review of output-preserving A100
optimization ideas. It does not authorize or prescribe a paid experiment.

## Evidence and execution path

- The frozen U02 graph uses node 58,
  `MiniMaxH3MemoryEfficientSageAttentionPatch`. It does not use
  `MiniMaxLowVRAMAttention` or set `minimax_head_chunks`; the latter's
  head-chunking path is not part of the measured run.
- The archived KJNodes patch dispatches SM80 to per-thread INT8 Q/K
  quantization (`BLKQ=128`, `WARPQ=32`, `BLKK=64`, `WARPK=64`), converts V to
  FP16, then calls `qk_int8_sv_f16_accum_f32_attn`. This is an FP32
  accumulator path, **not** an all-FP16 attention computation. The archived
  source is in `source-only.tar` below; runtime profiler events confirm that
  the SM80 attention kernel executed.
- The saved SageAttention 2.2.0 wheel contains an `_qattn_sm80` binary whose
  embedded architecture strings identify `sm_80` only. The build log names
  target capability `8.0`; therefore this run was not silently using an
  incompatible 5090 binary or the bypass-attention graph.
- A saved source tar and build manifest **do** pin the build input by SHA-256,
  although they do not identify an upstream Git commit. The archived
  `setup.py` declares `-O3`, `--use_fast_math`, `-Xptxas=-v`, and SM80
  targeting; the archived CUDA source fixes the FP32-accumulator branch's
  tile and quantization-scale shape contract. `ninja: no work to do` in the
  captured build log means this log does not expose the executed NVCC command
  or register/shared-memory report. Local `cuobjdump` and `nvdisasm` are
  unavailable, so occupancy is still unmeasured.

Artifact identities:

| Artifact | SHA-256 |
| --- | --- |
| `/mnt/d/comfyui-h3-backups/rental-20260924-5090/source-only.tar` | `db6e20a71fe6ac87c7a4a981f08ae0685db7c0229d3db5bdd5b51f0832ab1fc7` |
| `/mnt/d/comfyui-h3-backups/rental-20260924-5090/a100-perf-pilot/h3-sage-sm80-source.tar` | `42651d8da657de9cae5ca291012cf0d4f3aec9e9f878f15cb8b7cfa4b59aaad6` |
| `/mnt/d/comfyui-h3-backups/rental-20260924-5090/a100-perf-pilot/sageattention-2.2.0-cp313-cp313-linux_x86_64.whl` | `36fb6b6febdcd71aa171fa207291b40696a5f4384451100348a1ebdfec8a8238` |

## What the measurements support

The full U02 S1 control took 1323.563 s server-side, including 1206 s in
the 12-step sampler. The one-step profiler attributed 86,567.788 ms of CUDA
device time to the Sage attention operation, with the same 86,567.788 ms
reported for its nested CUDA kernel. These are overlapping aggregates, not
independent critical-path terms to add. The existing profile has no timeline,
stream view, Q/K/V shapes or kernel resource counters. It supports
**prioritizing attention investigation**, not a claim that attention is the
exclusive wall-time bottleneck or that A100 is at its hardware ceiling.

Removing `--disable-smart-memory` in the full S1/M1 comparison did not help:
server time improved 0.16%, sampler time 0%, while sampled VRAM peak rose from
35,910 to 51,396 MiB. The output media essence and AV latent matched for
that flag-only comparison. The current measured configuration already has
substantial unused VRAM; `head_chunks=2` offers no demonstrated speed
mechanism here and adds sequential attention calls. It remains a memory
fallback, not the next performance candidate.

Changing the FP32 PV accumulator to FP16, retuning tile sizes, changing
quantization boundaries or changing steps/model/precision may change the
output. None is an approved quality-preserving optimization based on this
audit. CUDA Graphs are also a low-priority hypothesis until a timeline shows
material launch gaps around the long attention kernels.

## Decision and next gate

**No concrete, low-risk, output-preserving speed patch was found offline.**
Stop here rather than consume another A100 session merely to search for one.
This is not proof that no improvement exists. The captured source and manifest
are sufficient to start a reproducible candidate design, but not to infer
runtime occupancy. Before a targeted kernel A/B, obtain a bounded live trace
with real Q/K/V shapes, launch gaps and kernel resource data. Limit collection
time, bytes and disk use; require a separately approved CU cap and automatic
stop. Advance only a candidate with a specific resource-level mechanism and
an end-to-end timing prediction. Suggested research gates from the review:
at least 1.20x in a same-wrapper microbenchmark before full U02, then at
least 10% full-U02 server-wall improvement, both with identical frozen input
and independent output-quality acceptance. These are proposed stop rules,
not measured performance gains.

The current A100 S1 is a fixed-input performance control, **not** a
user-accepted original-quality reference. The deferred human Sage-versus-
bypass review and an approved same-input rental 5090 reference are separate
quality gates. Numeric-equivalence claims or matching latents in a narrow
flag A/B cannot substitute for them. Receipt polling and normalized MP4
comparison should be fixed before any future paid run to avoid billed idle;
they are operational improvements, not sampler acceleration.

Detailed run data: `2026-09-26-h3-a100-combined-results.md`. CUDA Graphs
background: https://docs.nvidia.com/cuda/cuda-programming-guide/04-special-topics/cuda-graphs.html.
