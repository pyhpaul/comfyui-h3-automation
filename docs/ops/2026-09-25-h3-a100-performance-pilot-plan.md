# H3 A100 performance pilot: reviewed execution contract

Status: implementation-ready experiment plan, not a measured speedup or a
production migration decision. No GPU run or code change was authorized by
this document. Date: 2026-09-25.

## Decision and evidence

The unchanged EP04 manual-v16 U02 `motion_latent` one-pass prompt took 1564.983 s
on Colab A100-SXM4-80GB; its 12 sampler steps took about 1447 s. The rental
RTX 5090 client log places the corresponding U02 success between 646 and 656 s
after submission. The rental parent latent and the Colab parent latent came
from their respective U01 runs and are not a byte-matched GPU comparison.
The rental time is a polling interval, not a server-side execution trace.

Evidence: `docs/ops/2026-09-24-colab-u02-results.md`,
`runs/ep04_manual_v16_u01_u09_motion_latent.log`, and the saved U02 prompt
histories under the D: rental backup. A100's 35,566 MiB historical VRAM value
is the maximum of 5-second samples, not a continuous or allocator peak.

The saved rental prompt routes UNet through
`MiniMaxH3MemoryEfficientSageAttentionPatch`; the A100 `auto` profile routes
UNet directly into the LoRAs (`rtx4080(bypass)`). The profile name is a
fallback label, not a claim that A100 is an RTX 4080. The A100 log says
`Using pytorch attention`, but the archived ComfyUI code calls PyTorch SDPA,
which can dispatch a fused kernel. No actual SDPA kernel trace exists yet.

The archived KJNodes `nodes/ltxv_nodes.py` implements the same H3-specific
patch for multiple architectures. On SM80 its branch uses INT8 Q/K and FP16 V
with FP32 accumulation; on the rental SM120 branch it uses FP8 V. Reusing the
H3 node is therefore a viable *candidate*, but the rental Python 3.12/SM120
binary cannot be reused on Colab Python 3.13/SM80. The node is a compound
attention implementation (QKV lifetime, K mean subtraction, quantization and
kernel), not a single-kernel substitution. Its benefit and quality must be
measured as a whole.

## Frozen workload and allowed changes

Use the exact U02 source job and freeze SHA-256 for all six model files, all
four reference images, the prompt text, and the *same* Colab U01 AV latent.
Keep the two LoRA strengths, seed, 13-second request, 1 MP portrait canvas,
24 fps, beta 16-step schedule split to 12 executed Euler steps, one pass,
`motion_latent`, and output format. Do not change weights, reference sizing,
resolution, sampling schedule, Turbo settings, or prompt to make a candidate
look faster. Outputs are not required to be byte-identical: Sage attention is
an approximate-computation candidate and requires audiovisual review.

For each candidate, compare normalized submitted prompt graphs. Whitelist
only the candidate attention node and its UNet-to-LoRA edge, plus unique MP4
and AV-latent output prefixes. Runtime-only memory trials have no prompt graph
change. Any other graph or input-byte difference invalidates that comparison.

## Preparation and diagnostic gate

1. Keep A100 `auto` on `bypass` until a candidate is accepted. Add an explicit,
   opt-in A100 profile only when implementing the experiment. Keep the rental
   5090 profile unchanged and make rollback a one-parameter selection.
2. Build a pinned SageAttention wheel for Python 3.13, Torch 2.14/CUDA 13 and
   SM80 without spending A100 time if an equivalent build environment is
   available. Record source commit/archive hash, wheel hash, build command,
   CUDA architecture/ABI and dependency manifest. Install with `--no-deps`
   after checking prerequisites. Both baseline and candidate runs must use
   the same venv *after* installation; a dependency upgrade is not an
   attention-only experiment.
3. On the assigned A100, verify identity, compute capability 8.0, available
   VRAM, driver, power/clocks and runtime source hashes. Fail closed if the
   assignment is not the planned A100-SXM4-80GB or the frozen assets differ.
4. Diagnose the actual H3 sampling critical path on the unmodified bypass
   graph: SDPA kernel names, attention and GEMM time, host-to-device transfers
   on the critical path, allocation peaks, and clocks. GPU utilization alone
   does not distinguish compute, memory bandwidth or overlapped offload.
   A profiled one-step full-shape job is diagnostic only and is never a
   performance sample. If profiling facilities are unavailable, mark the
   causal diagnosis uncertain rather than guessing.
5. The archived H3-specific patch preflight must verify `_cuda_archs[0]` is
   `sm80`, `_qattn_sm80` and the required function exist, the extension's
   target architecture and ABI match, and a real H3-shape/stride/head-dim-128
   call finishes with finite output. Check that every intended H3 DiT block
   is patched and actually invokes the SM80 path. Unpatched Qwen, VAE or
   other non-DiT SDPA calls are not a fallback failure. A tiny synthetic
   import/probe or node-registration success alone is insufficient.

## Candidate order

Use the diagnostic trace to choose the first branch; do not run all variants
blindly.

- If H3 attention is material on the step critical path, first compare the
  archived H3-specific Sage node rebuilt for SM80 against bypass. This is the
  closest graph-level counterpart to the rental path, but not the same FP8
  arithmetic. If it fails compatibility, quality or benefit gates, consider
  KJ's targeted FlashAttention-2 node as a separate candidate. Pin FA2;
  reject its implicit FA3 fallback on A100. Validate H3's container unwrap,
  HND/NHD layout, full sequence lengths, masks, dtypes and actual call count.
  PyTorch SDPA may already use fused FlashAttention, so FA2 is not assumed
  faster merely because it is an external package.
- If *unoverlapped* model transfer is material on the sampling critical path,
  test removing `--disable-smart-memory` as a separate runtime-only candidate.
  Its archived ComfyUI behavior affects model unloading and initial placement;
  removal is not proof that per-step traffic will fall. Continue only if the
  trace and full-run result support it.
- Treat `--highvram` as a later, distinct memory regime: in this ComfyUI
  snapshot it also disables default dynamic VRAM and is mutually exclusive
  with `--lowvram`. Do not approve it from the 5-second VRAM samples alone.
  Require allocator and device-memory peaks plus a safety margin first.

Do not combine attention and memory changes in the initial A/B. Do not test
`--gpu-only`, new checkpoints, `ref_image_size=match`, fewer steps, lower
resolution, global `--fast`, compiler or CUDA graphs in this same-workload
pilot. Those are separate quality/performance programs.

## Measurement contract

Before formal timing, prewarm both modes with one actual H3-shape sampler
step, keeping the on-disk Triton/CUDA compilation cache. Charge and record
prewarm/compilation time separately. Each formal U02 sample restarts the
ComfyUI process to clear node cache and patch state; therefore the comparison
is same-VM, process-cold, disk-JIT-prewarmed, not warm-process inference.
If compilation still occurs in a formal sample, report that startup cost and
do not claim proven steady-state timing.

Run B1-C1-B2-C2, where B is bypass and C is exactly one candidate. Use
unique MP4 and AV-latent output prefixes per run, but no other workload
change. For every run,
preserve the submitted prompt, history, new prompt ID, all 12 sampling-step
timestamps, new MP4/AV latent, logs, five-second telemetry and hashes.
History success or a changed MP4 timestamp without 12 executed steps is not
a valid sample. Profiler-instrumented runs are excluded from timing.

Report ComfyUI server wall time, sampler wall time, median and spread of
steps 2-12, restore/setup/prewarm/backup wall times, actual CU rate and
balance snapshots. The historical 5090 ~10m50 is an external target, not
the B/C denominator. Pilot screening passes only if both paired comparisons
improve sampler **and** full server time by at least 15%, baseline runs differ
by no more than 10%, and no correctness/quality gate fails. Otherwise report
failure or inconclusive; two pairs cannot establish broad reliability or
5090 parity. A future second clean-runtime repeat is required before a
reliability claim.

## Quality and continuation gates

The prior A100 U02 is technically successful but has no signed-off visual
quality baseline. Prepare randomized baseline/candidate full videos for the
user or a designated human reviewer. The fixed checklist is: first/last
second seam, identity and clothing, blocking/position and prop continuity,
shot and dialogue adherence, temporal flicker, lip/audio sync, distortion
and clipping. No agent-only contact-sheet review can sign this gate.

Automated checks require the expected duration, frames/fps/resolution,
non-silent audio track and synchronization, plus finite AV latent with the
expected shape/dtype/layout and a successful U03 context-load smoke. This
permits only a U02 pilot result. Promotion of the `motion_latent` chain needs
separately budgeted full U03 continuation from both B and C U02 latents and
human review. The baseline and candidate need not produce identical pixels.

## CU admission and shutdown

No GPU assignment starts without a separate execution authorization. Use a
diagnostic-stage hard cap of 4 CU and a later formal A/B-stage cap of 20 CU;
these are *ceilings*, not guaranteed sufficient budgets. The diagnostic gate
does not include a full U02 timing run. On the historical 6.77 CU/hour rate,
the 15.2-minute restore alone cost about 1.7 CU. If the diagnostic cannot
finish inside its cap, stop and report incomplete evidence; do not extend it
silently. A formal batch may need a fresh restore if approval is delayed;
include that restore in the formal cap. U03 validation has its own approval.

Before every paid phase and every full run, compute
`required_CU = current_rate_CU_per_hour * planned_max_wall_hours + 1.0`.
Admission requires `required_CU` to be no greater than **both** the account
balance and the unspent stage cap. The 1 CU is reserved for capture, backup
and shutdown. Use a 35-minute hard limit per full prompt and a 25-minute
maximum for compilation/diagnostic work, subject to the tighter CU cap.
Do not omit B2/C2 or quality review and claim a pass merely to fit budget.
No automatic full-run retry follows OOM, NaN, missing SM80 calls, unplanned
backend fallback, missing 12 steps, quality failure or budget breach.

A host-side watchdog owns the stop deadline. In all success/error paths,
save evidence, issue `colab stop`, then verify `colab usage` shows zero active
assignments and zero rate and `colab sessions` shows no live session. Do not
leave a paid VM idle while waiting for approval. Run consecutive accepted U
units in one VM when authorized to amortize the ~15-minute restore, but
report that operational saving separately from per-prompt inference speed.

## Three adversarial review rounds

- Round 1, Astra: **FAIL**. Found node-cache false-speedup risk, non-byte-
  equivalent attention outputs, incomplete quality/continuation checks,
  misleading high-VRAM/offload assumptions and unbounded cost/repeats.
- Round 2, Astra: **P0 closed; P1 open**. Required same dependency environment,
  compound-patch attribution, explicit SM80 extension preflight, disk-JIT
  prewarm accounting, budget admission and paired variability gate.
- Round 3, Astra: **PASS** for this implementation-ready controlled pilot
  contract. It is not acceptance of a speedup, video quality, full-chain
  reliability or Colab replacing the rental RTX 5090.

## Primary technical references

- Archived runtime source: `source-only.tar` in the D: rental backup,
  `ComfyUI/comfy/cli_args.py`, `comfy/model_management.py`,
  `comfy/ldm/modules/attention.py`, and
  `custom_nodes/ComfyUI-KJNodes/nodes/ltxv_nodes.py`.
- NVIDIA CUDA feature/precision matrix:
  https://docs.nvidia.com/cuda/cuda-programming-guide/05-appendices/compute-capabilities.html
- PyTorch SDPA backend selection:
  https://docs.pytorch.org/docs/main/generated/torch.nn.attention.sdpa_kernel.html
- SageAttention SM80 extension source:
  https://github.com/thu-ml/SageAttention/blob/main/setup.py
- FlashAttention-2 A100 support and benchmark scope:
  https://github.com/Dao-AILab/flash-attention/blob/main/README.md
- ComfyUI H3 reference sizing and conditioning:
  https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_extras/nodes_minimax_h3.py
