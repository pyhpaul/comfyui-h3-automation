# A100 H3 Sage pilot: first diagnostic run

Date: 2026-09-25. Scope: compatibility smoke only. The formal B1-C1-B2-C2
performance comparison and audiovisual quality gates in
`2026-09-25-h3-a100-performance-pilot-plan.md` have **not** run.

## Result

- The experimental `a100_sage_sm80` profile is explicit-only. `auto` still
  selects bypass on A100; the RTX 5090 profile is unchanged.
- An SM80 SageAttention 2.2.0 wheel was built on a CPU-only Colab VM for
  CPython 3.13, Torch 2.14.0+cu130, CXX11 ABI 1 and CUDA 13.0. The wheel
  imports `_qattn_sm80` and `_fused`; the required
  `qk_int8_sv_f16_accum_f32_attn` symbol exists. CPU import does not prove GPU
  correctness.
- On a new A100-SXM4-80GB / SM80 runtime, the restored EP04 manual-v16 U02
  `motion_latent` graph with the Sage profile finished a **single-step,
  full-shape** diagnostic prompt. The ComfyUI log recorded application of
  the H3-specific Sage patch, and the runner returned `SUCCESS` with a new AV
  latent path after 143.19 seconds. The probe removed the MP4 output node and
  set `SplitSigmas.step=1`; it was not a full U02 and has no valid speedup
  denominator. The latent and `/history` were not backed up before shutdown,
  so finite-tensor, per-block SM80-call and quality gates remain open.

## Reproducible environment and artifacts

| Item | Observed value |
| --- | --- |
| GPU | NVIDIA A100-SXM4-80GB, compute capability 8.0, 85,094,825,984 B VRAM |
| Driver / power / max SM clock | 580.82.07 / 400 W / 1410 MHz (`nvidia-smi`) |
| Fresh VM system Torch | 2.11.0+cu128; changed from the earlier clean A100 run |
| Experiment venv Torch | 2.14.0+cu130, CUDA 13.0, CXX11 ABI 1; install 23.3 s |
| Sage source tar SHA-256 | `42651d8da657de9cae5ca291012cf0d4f3aec9e9f878f15cb8b7cfa4b59aaad6` |
| SM80 wheel SHA-256 | `36fb6b6febdcd71aa171fa207291b40696a5f4384451100348a1ebdfec8a8238` |
| Drive model restore | 853.54 s for models, 871.84 s total; six model files verified by the prior restore script |
| ComfyUI setup | 49.74 s including pinned wheel install and HTTP readiness |
| Candidate diagnostic | prompt `00d44be4-4bed-4d3b-b061-3a2709a7f8d2`, 143.19 s runner wall, one executed sigma step |
| Paid session | 15:05:36-15:30:51 UTC, 25 min 15 s; 6.77 CU/h |
| CU estimate | 179.43 before GPU assignment, 176.59 after final settlement; approximately 2.84 CU for the whole paid session, below the 4 CU diagnostic ceiling |
| Shutdown | `Active assignments: 0`, `Usage rate: 0.00/hr`, `colab sessions`: none |

The source tar includes the archived rental SageAttention source with its
existing C++20 setup adjustment. The first CPU build attempts exposed three
toolchain issues: missing CCCL headers, a mixed `nvidia-nvvm` 13.4/`ptxas`
13.0 PTX-version mismatch, and a missing unversioned `libcudart.so` link.
The successful build pinned `nvidia-cuda-nvcc`, `nvidia-cuda-crt` and
`nvidia-nvvm` to 13.0, installed `nvidia-cuda-cccl` 13.0, and linked
`libcudart.so` to `libcudart.so.13` inside the isolated build venv. Exact
packages and build command are in `h3-sage-build-manifest.json`.

Local backup:
`/mnt/d/comfyui-h3-backups/rental-20260924-5090/a100-perf-pilot/`.
It contains the source tar, wheel, build log and manifest, diagnostic full
and one-step submitted graphs, partial ComfyUI and runner logs, the exported
Colab session history, and control scripts. The partial logs predate the final
`SUCCESS`; the session history contains that final runner result. The wheel
and two runner scripts are also in the dedicated Drive prefix
`comfyui-h3-colab-dedicated/rental-20260924-5090/a100-perf-pilot/`.

## Limits and next gate

This result proves that the opt-in graph can register and complete one
full-shape H3 sampler step on A100 with the rebuilt extension. It does **not**
prove a faster full U02, kernel call counts, finite AV latent contents,
baseline parity, video quality, U03 continuation, or production suitability.
The runtime source says the patch targets every H3 transformer block, but no
instrumented call trace was retained; do not infer actual SM80 invocation
count from the 208 total model patches in the log.

The initial detached `nohup` watchdog did not survive the host command
session. A foreground watchdog was started later and stopped the GPU within
the 4 CU cap, but the session lasted 15 seconds beyond the planned 25-minute
wall limit. Use `scripts/ops/colab_h3_paid_watchdog.sh` in a retained host
command session with an **absolute UTC deadline** before the next assignment.

Before formal A/B, repeat a bounded diagnostic that retains `/history`, the
new AV latent and a finite-tensor check, plus an actual attention/SDPA kernel
trace or explicitly mark the causal hypothesis unverified. Stage the wheel via
Drive rather than `colab upload`: the latter stalled on this 8.4 MiB file,
whereas local-to-Drive rclone finished in about 7 seconds. No formal timing
run should start until the frozen inputs and CU admission are rechecked.

## Follow-up diagnostic: retained one-step evidence

The second, separately admitted diagnostic ran on 2026-09-25. It used a fresh
A100-SXM4-80GB / SM80 high-memory Colab runtime with the same pinned experiment
Torch 2.14.0+cu130 and SM80 wheel. The six restored H3 model files and U01
parent latent passed the restore script's size/hash checks. The source patch
added only an opt-in log immediately after the SM80 extension call; this
instrumentation was **not** applied to the repository or used for a formal
timing comparison.

| Item | Observed value |
| --- | --- |
| Session | `h3-a100-diag2-20260925`, 15:46:25-16:06:48 UTC (20 min 23 s) |
| Restore | 857.75 s total, 841.06 s model stage |
| ComfyUI setup | 53.48 s including wheel and HTTP readiness |
| Probe | EP04 manual-v16 U02, `motion_latent`, one full-shape sampler step; prompt `c5c56f85-1b39-4732-ae12-68269f5ae865` |
| Probe duration | 145.39 s runner wall; ComfyUI reports 140.19 s prompt execution |
| ComfyUI history | `status_str=success`, `completed=true`, output nodes `263` and `405`; MP4 node `264` deliberately removed |
| SM80 trace | 50 logged calls to `_qattn_sm80.qk_int8_sv_f16_accum_f32_attn` after successful return, each with `q=[1,121652,56,128]`, `v=[1,121652,56,128]`, `bfloat16` output |
| AV latent | `ep04_u02_diag_candidate_00002.safetensors`, 38,580,184 B, SHA-256 `a294dc094bc93748403b873311fb98f2d30b5cba6e563987476cf3d58c339ec0` |
| Finite check | `audio=[1,32,2,547]` and `video=[1,24,97,86,48]`, both float32 and all finite |
| CU | 176.59 before, 174.41 after: 2.18 CU observed; under the second run's fresh 4 CU ceiling |
| Shutdown | Manually stopped before the 16:11:14 UTC watchdog deadline; `Active assignments: 0`, `Usage rate: 0.00/hr`, no active sessions |

Evidence is on Drive under
`comfyui-h3-colab-dedicated/rental-20260924-5090/a100-perf-pilot/diagnostic-2/evidence/`
and copied to
`/mnt/d/comfyui-h3-backups/rental-20260924-5090/a100-perf-pilot/diagnostic-2/`.
The local latent SHA-256 matches the remote recorded digest. The D backup
includes the full and submitted one-step graphs, `/history`, finite check,
ComfyUI and runner logs, the 38.6 MB latent, and Colab session history.

The new log proves execution of the SM80 extension at this call site, but it
is **not** a CUDA profiler kernel trace and does not measure kernel duration.
It also does not establish numerical parity with the bypass path, a full U02
speedup, audiovisual quality, or long-run stability. Those remain formal A/B
and quality gates. The 145.39 s value is an instrumented single-step smoke,
not a per-video benchmark or a 5090 comparison.

The two separately admitted diagnostics consumed approximately 5.02 CU in
aggregate (first 2.84, second 2.18); this exceeds the original plan's single
4 CU diagnostic-stage cap, which is why the second run was explicitly scoped
as a fresh bounded diagnostic before starting. No formal-stage CU was used.
