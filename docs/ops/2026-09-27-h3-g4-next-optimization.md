# H3 G4 next optimization discussion (no paid run)

## Baseline and objective

Keep the frozen EP04-U02-v16 graph, 12 sampler steps, 768x1376/24 fps output,
motion-latent continuity, reference inputs and quality threshold. The first G4
run produced one validated U02 in 520.258 s server wall (479 s sampler) on an
RTX PRO 6000 Blackwell. The 5-second GPU samples averaged 94.4% utilization
and peaked at 35,807 MiB VRAM. The single cold assignment used 627.11 s to
restore assets and 541.11 s for the run phase.

Do not optimize by reducing resolution, frames, steps, prompt detail, reference
assets, or output validation. A single sample and sparse sensor data are not a
causal performance profile. The visual blind screen was close to the 5090
sample, but continuous viewing and audio listening are still pending.

## Ranked opportunities

### 1. Batch successive units in one G4 assignment

The 10.1-minute model restore is paid every fresh assignment. The first
priority is a controlled `U02 -> U03 -> ...` same-session motion-latent chain:
verify each parent's hash and graph before queueing the next unit, keep one
ComfyUI instance alive, and publish each verified unit to Drive before moving
on. Per-unit Drive backup is preferable to waiting until the entire chain ends:
the first G4 MP4 plus latent was about 48.5 MB, small beside the 41.65 GB
model restore, while Colab runtimes are ephemeral.

At the observed 8.90 CU/hour, the first-run 627 s restore represents about
1.55 CU. The 541 s generation phase represents about 1.34 CU. Sharing the
restore across five similarly sized units could reduce the modeled fixed
cost per unit substantially, but the actual five-unit rate, cache behavior,
failure handling and CU settlement must be measured in one authorized batch.
At 8.90 CU/hour the measured restore stage is equivalent to about 10.45
minutes of idle G4 time; this is a rough warm-session keep/stop break-even,
not an implemented scheduler policy. The first phase exceeded Comfy server
wall by only about 21 seconds, which includes startup, validation and backup;
deferring every output to a final batch upload is unlikely to recover the
10-minute model restore and would increase ephemeral-output loss risk.

### 2. Profile the G4 sampler before changing kernels

Sampling accounted for 479/520 s (about 92%) of server execution. A detailed
torch/CUDA trace on one approved unit should distinguish attention kernels,
model matmul, host-to-device transfers, allocator pauses and text/video decode.
The high sampled GPU utilization does not prove every model stayed resident;
the 35 GiB VRAM peak was observed under `--lowvram` on a 96 GB device.

### 3. Test memory residency without changing the graph

Only after the profile, compare the existing startup flags with a G4-specific
memory-resident candidate (for example, disabling `--lowvram` while retaining
the same attention patch and graph). Use a same-session order-balanced pair,
capture peak reserved/allocated VRAM, transfer traffic, sampler and server
timing, and compare both latent and decoded media. Stop on OOM, instability or
visual/audio regression. Do not infer a speedup merely from available VRAM.

### 4. Consider kernel/runtime changes only behind quality gates

The current G4 wheel targets SM120a, and the KJNodes MiniMax patch follows its
SM120 path. A different SageAttention implementation, CUDA graphs or
`torch.compile` may change outputs or increase warmup/compilation time. These
are research candidates, not default settings. Require a frozen graph/input,
repeat timing, kernel trace, successful latent-chain continuation and blinded
audiovisual review before promotion. Two concurrent U02 prompts are not a
default optimization: the GPU was already busy, and parallelism can worsen
single-clip latency even if 96 GB VRAM fits both.

## Next measured gate

No GPU is needed to finish the current documentation and artifact contract.
The next paid gate should be **one G4 assignment with multiple sequential
units**, not repeated one-unit cold starts. Freeze the exact units, parent
latents, maximum wall/CU safety rule, terminal receipts and stop conditions
before allocation. Record allocation, restore, setup, each prompt, backup,
idle gaps, CU snapshots and post-stop state. Treat visual quality, timing,
stability and monetary cost as separate decisions.

The source-controlled restore/preinstall scripts and new Drive output prefix
have passed offline tests only; the tested G4 run used their earlier D: copies
and the historical output prefix. Validate the new operational packaging on
the next already-authorized paid session before calling it production-ready.
