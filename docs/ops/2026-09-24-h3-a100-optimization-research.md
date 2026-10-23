# MiniMax H3 on A100 80GB: quality and throughput research

Status: research archived on 2026-09-24. All experiments below are deferred
until the unchanged EP04 U02 `motion_latent` continuity gate is complete. This
document does not authorize a new GPU allocation, model download, or workflow
change. The active portability record is `2026-09-24-colab-portability.md`.

## System boundary

The current workflow is a functioning H3-Base Ref2VA audio-video generator,
not MiniMax's complete H3 system. The hosted H3-Context-IR and
H3-Regenerate-2K stages are not available for local deployment. The project's
optional 3D latent-upscale second pass is not the official regeneration API.
Additional VRAM can enable different weights and reduce offload; compute alone
does not add the hosted stages or improve reference/prompt correctness.

## Verified project baseline

- Colab Pro provided one A100-SXM4-80GB runtime with 81,153 MB reported VRAM
  and 171,061 MB reported host RAM. EP04 U01 generated a 12.25-second,
  768x1376, 24 fps H.264/AAC output and AV latent in one pass. ComfyUI reported
  18m34s prompt wall time; the 12-step sampling progress bar occupied about
  17m05s. This is one U01 observation, not a U02 or repeated-run benchmark.
- The current graph uses a community b25-49 hybrid pruned int8 DiT, a
  15.7 GB NVFP4-AWQ Qwen encoder, int8 video VAE, FP32 audio VAE, Turbo v4
  LoRA at 1.0, MysticXXX LoRA at 0.2, a beta 16-step schedule split after
  step 12, `ref_image_size=max`, and 1.0 megapixel portrait output.
- `gpu_profile=auto` maps A100 to the `rtx4080` bypass-attention path, not the
  RTX 5090-specific Sage FP8 patch. The rental startup script also sets
  `--lowvram --reserve-vram 4 --disable-smart-memory --force-fp16
  --disable-cuda-graphs`. The A100 log reports `LOW_VRAM`, dynamic VRAM,
  async weight offloading, native int8 ops, and emulated NVFP4 ops.
- The six selected model files total 38.79 GiB on disk. This is not measured
  peak VRAM. U01 reference images are about 1.57 megapixels each while the
  output canvas is 1.06 megapixels. `ref_image_size=match` would downscale
  each reference to output pixel area; `max` retains the original dimensions
  because their short edges are under 2048 px.
- Sampling-time GPU utilization, peak/resident VRAM, host-to-device traffic,
  per-node timings, and visual acceptance are not yet measured. Aggressive
  offload and large reference tokens are plausible bottlenecks, not proven
  causes of the observed 85-second average sampling step.

Evidence: `colab-stage1/colab-comfy.log`, `colab-stage1/job.yaml`, and the
saved U01 outputs under `D:\comfyui-h3-backups\rental-20260924-5090`;
`scripts/ops/comfy_gpu_start.sh`, `src/comfy_orch/gpu_adapt.py`,
`src/comfy_orch/render_profile.py`, and
`templates/yz_h3_ep_unit/workflow_api.json` in this repository.

## Deferred A100 experiment order

1. Preserve the unchanged U02 success artifact and timing. On the next
   comparable run, collect prompt phase timings, per-step time, GPU utilization,
   peak VRAM, host RAM, and offload/transfer evidence. Separate restore/setup
   time and CU from inference time and CU.
2. With current weights and references, change only the runtime memory policy:
   compare the present startup flags against a run without
   `--disable-smart-memory`. The pinned ComfyUI CLI says this flag aggressively
   offloads to RAM; `--lowvram` may be inert while dynamic VRAM is enabled.
   Do not infer a speedup without telemetry. Test normal/high-VRAM policies
   only after observing headroom; keep the original script as rollback.
3. Compare `ref_image_size=max` and `match` on a fixed representative input.
   The lower token load may reduce every sampling step, but it can weaken
   identity fidelity. Score both, rather than optimizing time alone.
4. Benchmark a separately installed A100/SM80-compatible attention path
   against the current bypass path. Do not apply the 5090 SM120 FP8 patch to
   A100. Sage attention is approximate; compare synchronized audio, identity,
   detail, and temporal stability as well as speed.
5. Run quality-only A/B tests, one change per run: complete the U01 prompt
   timeline (the 12-second job's shot descriptions stop at 9.5 seconds), make
   subject/reference roles explicit, disable the extra style LoRA, evaluate
   Turbo v4 with a compatible scheduler/step recipe, and test the FP16 video
   VAE already present in the D: backup. Do not change the U02 baseline.
6. For checkpoint comparison, start with Comfy-Org's native pruned int8
   Ref2VA DiT (about 21 GB) against the current approximately 21 GB hybrid
   under otherwise fixed inputs. Next, assess pruned BF16 Ref2VA (40.2 GB).
   The unpruned BF16 Ref2VA single-file DiT is 66.3 GB; together with even
   the existing 15.7 GB Qwen encoder it exceeds one 80 GB GPU before VAEs,
   LoRAs, activations, or references, so expect offload and a speed tradeoff.
   A 27.1 GB int8 Qwen may avoid NVFP4 emulation on A100, but text/reference
   encoding is not the observed dominant 17-minute sampling phase.
7. Only if spatial/temporal adherence remains poor, evaluate native
   `MiniMaxH3AddGuide` anchors or the project's second pass in isolated
   experiments. Confirm compatibility with the existing `motion_latent`
   chain; the second pass is not equivalent to official H3-Regenerate-2K.

Use a fixed prompt, seed, references, parent latent where applicable, and
output profile for each single-variable comparison. A short clip is a cheap
screening test; confirm the chosen setting at full production duration and
inspect the video and audio, not only a similarity metric or exit code. Keep
all successful outputs and timing/CU metadata outside the ephemeral VM.

## Primary references

- MiniMax system and checkpoint contracts:
  https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/README.md
- MiniMax Ref2VA rewrite guide:
  https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md
- ComfyUI H3 reference sizing and guide-node implementation:
  https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_extras/nodes_minimax_h3.py
- ComfyUI startup-flag semantics:
  https://github.com/Comfy-Org/ComfyUI/blob/master/comfy/cli_args.py
- Comfy-Org checkpoint file sizes and encoder advice:
  https://huggingface.co/Comfy-Org/MiniMax-H3/tree/main/diffusion_models
  https://huggingface.co/Comfy-Org/MiniMax-H3/tree/main/text_encoders
  https://huggingface.co/Comfy-Org/MiniMax-H3/blob/main/README.md
- Turbo v4 author-recommended scheduler and step range:
  https://huggingface.co/mu1998/MiniMax-H3-Turbo-Lora/blob/main/README.md
- SageAttention SM80 implementation:
  https://github.com/thu-ml/SageAttention/blob/main/setup.py
