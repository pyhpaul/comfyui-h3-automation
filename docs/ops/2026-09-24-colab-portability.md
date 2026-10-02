# Rental H3 capture and Colab portability (2026-09-24)

## Source of truth

The rental instance was already booted from the provider's saved image. Its
autostarted `/root/ComfyUI` process was stopped after checking its PID and CWD.
The team instance at `/root/autodl-tmp/ComfyUI` was started using the exact
`scripts/ops/comfy_gpu_start.sh` content and the vm122 tunnel was switched.
The local and remote start scripts had the same SHA-256:
`3706aded3e6ab7ca0806b13f8c09dd5081f28aae522ce18a0dae839633b6d62d`.

The live team instance reports ComfyUI 0.34.0, Python 3.12.3, PyTorch
2.14.0+cu130, CUDA 13.0, and RTX 5090 with 32,607 MiB physical VRAM.
`/system_stats`, `/queue`, and all 23 node classes required by
`templates/yz_h3_ep_unit/workflow_api.json` were checked. No H3 generation
was queued during this capture.

## Filesystem and backup boundary

`/root/autodl-tmp/ComfyUI` is on the container overlay filesystem, not on
the `/models`, `/poddata`, or `/usrdata` NFS mounts. There are no symlinks
under the team ComfyUI tree outside `.venv`. Approximate source sizes:

| Path | Size | Meaning |
| --- | ---: | --- |
| `ComfyUI/models` | 45 GiB | H3 models, encoder, VAEs, LoRAs, upscaler |
| `ComfyUI/.venv` | 8.5 GiB | Rental-specific Python environment |
| `ComfyUI/output` | 8.4 GiB | Historical output and latent context |
| `ComfyUI/input` | 1.2 GiB | Uploaded input assets |
| `ComfyUI/custom_nodes` | 101 MiB | Custom node source |
| `SageAttention-main` | 179 MiB | Local SageAttention build source |

The portable capture is stored under
`D:\comfyui-h3-backups\rental-20260924-5090` (`/mnt/d/...` in WSL):

| Artifact | Contents |
| --- | --- |
| `models.tar` | `ComfyUI/models` content, rooted at `models/` |
| `runtime.tar` | `autodl-tmp` except models, input, output, temp, live H3 log |
| `input.tar` | `ComfyUI/input` |
| `output.tar` | `ComfyUI/output` |
| `source-only.tar` | Colab staging source, without `.venv`, models, input, output, temp, live log |
| `ops.tar` | Selected `/root` startup and provider scripts for provenance |
| `pip-freeze.txt`, `dpkg-packages.txt`, `object-info.json` | Dependency and API inventory |
| `SHA256SUMS` | Local archive checksums after transfer validation |

All nine entries in `SHA256SUMS` passed a full local `sha256sum -c` readback
with exit 0, including the 45 GiB model and 8.9 GiB runtime archives.

This is an application/filesystem backup, **not** an OCI image or a bootable
export of the provider's saved image. The provider's own image remains the
provider-side restore point. Do not restore `runtime.tar` into a Colab hosted
VM wholesale: `.venv` embeds Python and CUDA binaries and absolute paths from
the rental instance.

### Restore layout (not yet tested on a clean rental instance)

On an equivalent rental base with Python 3.12 and a compatible NVIDIA driver,
extract `runtime.tar` into `/root/autodl-tmp`, then extract `models.tar`,
`input.tar`, and `output.tar` into `/root/autodl-tmp/ComfyUI`:

```bash
mkdir -p /root/autodl-tmp/ComfyUI
tar -xf runtime.tar -C /root/autodl-tmp
tar -xf models.tar -C /root/autodl-tmp/ComfyUI
tar -xf input.tar -C /root/autodl-tmp/ComfyUI
tar -xf output.tar -C /root/autodl-tmp/ComfyUI
```

Use the repository's canonical `scripts/ops/comfy_gpu_start.sh` after checking
the active platform process and port. `ops.tar` is evidence, not an instruction
to overwrite the provider's `/root/restart.sh` or `/root/link.sh`. Verify
`SHA256SUMS` before extraction and perform a clean-instance `/system_stats`,
node-class, and H3 run before declaring rental restore complete.

## Colab stage-1 result

Colab Pro allocated an A100-SXM4-80GB high-RAM runtime. Its initial kernel
was Python 3.13.15 with PyTorch 2.11.0+cu128. A fresh Python 3.13 venv was
built from `source-only.tar` and the source `requirements.txt`; it resolved
PyTorch 2.14.0+cu130, which passed a CUDA/A100 smoke check. The required
custom-node dependencies were installed separately. ComfyUI 0.34.0 started
with the rental startup flags, `/system_stats` reported the A100, and all 23
workflow node classes were registered. A 64x64 `EmptyImage` to `SaveImage`
API prompt completed before the H3 test described below.

The optional `ComfyUI_NVIDIA_RTX_Nodes` package did not import because
`nvvfx` was absent. None of the 23 required workflow classes depend on it.

The source-only Colab staging steps already exercised were:

```bash
mkdir -p /content/h3-rental
tar -xf source-only.tar -C /content/h3-rental
uv venv --python /usr/bin/python3.13 --system-site-packages \
  /content/h3-rental/ComfyUI/.venv
uv pip install --python /content/h3-rental/ComfyUI/.venv/bin/python \
  -r /content/h3-rental/ComfyUI/requirements.txt
```

The relevant custom-node requirements for KJNodes, VideoHelperSuite,
Easy-Use, and kaytool were installed separately. Keep the source archive and
dependency manifest outside the VM because these steps must be repeated when
Colab replaces the runtime.

The rental-to-Colab `rsync -a` of `ComfyUI/models/` completed with exit 0:
47,704,718,922 bytes in 45 files, occupying about 45 GiB on Colab. A second
`rsync -ani` reported no pending changes. ComfyUI `/object_info` lists the
required H3 UNet, Qwen3VL NVFP4-AWQ encoder, both VAEs, and both template
LoRAs. The EP04 manual-v16 U01 three reference images (6.8 MB total) were
uploaded separately; this avoids transferring the full historical input and
output directories for a chain-start probe. The documented U01 prompt audit
passes with no warnings. A non-video API prompt loaded the H3 UNet and a
second loaded the Qwen3VL encoder. A `CLIPTextEncode` probe then completed in
8.45 seconds on A100 (prompt ID `2e931d50-7b7d-4367-af45-bf67223da98b`).
The live ComfyUI log reported `MiniMaxH3TEModel_` staged at 14,956 MB with
`nvfp4` among the emulated operations. This verifies basic text encoding,
not full H3 conditioning, sampling, audio, or video output.

The signed-in Colab account's Google One page showed 5 TB total storage and
about 0.23 GB used on 2026-09-24. This was a read-only capacity check; Drive
was neither mounted nor written. A Colab CLI session-name cache issue briefly
orphaned the live assignment locally; the one server-side A100 assignment was
reattached without creating another VM.

## Full H3 stage-1 result

EP04 manual-v16 U01 was submitted as `motion_latent`, one pass, no parent
latent, with `gpu_profile=auto` resolving to the bypass-attention `rtx4080`
profile on A100. The bound 31-node workflow is saved as
`colab-ep04-u01-bound-workflow.json` in the D: backup directory. The actual
prompt ID was `916b0594-ab3f-4663-b979-71134da3a227`; ComfyUI history
reported `success` and the server log reported `Prompt executed in 00:18:34`.
The 12 sampling steps each took about 85.7 seconds after initialization.

The output was a 12.25-second, 768x1376, 24 fps H.264/AAC MP4 (8,076,481
bytes) plus an AV latent at `h3_context/ep04_u01_00001.safetensors`
(34,602,712 bytes). Both files were downloaded under
`D:\comfyui-h3-backups\rental-20260924-5090\colab-stage1` as
`EP04-U01-v16-colab-a100-pass1_00001-audio.mp4` and
`ep04_u01_00001.safetensors`. Local and Colab SHA-256 matched:

The same `colab-stage1` directory also contains the selected job manifest,
three reference images, prompt source/audit, ComfyUI history and server log,
and contact sheets for both Colab and rental outputs.

| Artifact | SHA-256 |
| --- | --- |
| MP4 | `57f94888bab3cf64a45ac076f7b7f04c085ba9e7d16a230f10bde2f24a2ce5d2` |
| AV latent | `6def89c01d367a64be354a93dfb7e96806d236211eb0fdfcbf4bfe493a95946a` |

The successful rental EP04 U01 baseline has the same duration, dimensions,
frame rate, and H.264/AAC tracks. A prompt-metadata comparison found only
the expected attention routing and output-prefix differences, plus two unused
blank image-loader nodes in the current template. Contact-sheet inspection
showed the same main scene progression; frame-level SSIM was 0.784, so the
outputs are **not pixel-identical**. The Colab audio stream is non-silent.
This proves one chain-start sample, not multi-unit latent continuity, visual
acceptance of a full episode, or a clean-VM automated rebuild.

`colab stop` was executed after collecting artifacts. `colab usage` then
reported 0 active assignments and 0.00 CU/hour. The measured balance moved
from 199.92 to 185.41 CU across setup, transfer, idle time, and inference;
14.51 CU is a whole-stage observation, not the cost of inference alone.

## Drive staging and CPU-only restore probe (historical progression)

For the one-pass EP04 U02 gate, six required model files were extracted from
the verified `models.tar` into D: staging (41,651,185,023 bytes / 38.79 GiB).
The UNet, Qwen3VL encoder, audio/video VAEs, and two LoRAs are sufficient for
the current template; the FP16 video VAE and latent upscaler are not selected.
At this checkpoint, local-to-Drive model upload was in progress and did not
require a Colab VM. It later completed and passed the selected-file checks
before the second A100 runtime was started; see the U02 result document.
The source-only archive, U02 job assets, and U01 parent AV latent have already
been uploaded. The Drive copy of the source archive and parent latent matched
their local MD5 hashes.

The original whole-file upload stalled on repeated retries of the Qwen and
video VAE files. A subsequent 512 MiB-part upload exposed the decisive error
in `drive-stage/logs/vae-parts.log`: Google Drive API HTTP 403,
`RATE_LIMIT_EXCEEDED`, for the shared rclone OAuth project's requests-per-minute
quota. This proves the shared project's API limit blocked that attempt; the
earlier whole-file retries had no DEBUG log, so their exact cause is not proven.
The part upload was stopped rather than continuing to hit the quota. The
already completed audio VAE and two LoRAs remain on the old Drive prefix.
Local splitting of the video VAE, Qwen encoder, and UNet completed into 6,
30, and 40 parts respectively; each part is at most 512 MiB, and the byte
sums match the three original files. No Colab GPU is running during this
transfer work.

The first Google Cloud Console tab had silently selected a different browser
account, which lacked MFA; that was not the Drive account used for this H3
staging. The actual Drive account was confirmed from its signed-in Drive home
and already has MFA. Its two existing Cloud projects are both unbilled;
creating a third was blocked by project-count quota. The first project had an
existing `openclaw` OAuth brand. A temporary H3 client created there was
deleted, its test user removed, and Drive API returned to disabled. The second
project (`tranquil-well-490216-i8`) had no OAuth brand and was used for the
dedicated `ComfyUI H3 Drive Restore` desktop client. Only Drive API was
enabled. Both project and client use `drive.file`, with no billing account or
paid quota. Client JSON and rclone config are mode 0600 under the local
`~/.config/rclone-h3/`, not in this repository or D: backup. A 10,200-byte
README upload through the new client matched local/remote MD5. The new Drive
prefix is `comfyui-h3-colab-dedicated/rental-20260924-5090` because the new
`drive.file` app cannot assume access to files created by the old app. The
video VAE part upload is the first large-file test through that prefix.
All six video VAE parts were uploaded through the dedicated client without
HTTP 403; `rclone check` reported six matches and zero differences. The
30-part Qwen encoder upload was the next transfer at that checkpoint. The local
Colab restore script has been adapted to fetch 512 MiB parts, reassemble
models while hashing, and avoid storing a second full copy of each model on
the VM. Its end-to-end clean-runtime behavior was later tested by the
successful U02 run.

The new OAuth app is still in Testing status. Google's documented Testing
refresh-token lifetime is seven days for `drive.file`; longer-term one-command
restore requires publishing the app and reauthorizing, or accepting periodic
reauthorization. Production publishing requires a verified owned domain and
public app/privacy pages, which are not available for this gate. The decision
is to keep Testing and finish U02, then revisit durable authorization later.
The GPU was not started until the entire selected model set was recoverable
from the dedicated Drive prefix.

A disposable **CPU-only** Colab session measured Drive-to-VM restore using
the 439,848,960-byte source archive: 5.83 seconds (71.91 MiB/s) with a
matching MD5. This is a small-file throughput probe, not proof that the
38.79 GiB model set will sustain that rate. The CPU session's observed usage
rate was 0.08 CU/hour, and it was stopped immediately after the probe;
`colab usage` again showed 0 active assignments and 0.00 CU/hour.

A second CPU-only session compared the same 536,870,912-byte video-VAE part
from two sources. WSL `/mnt/d` to Colab via `rsync` over the CLI's SSH
`ProxyCommand` took 133.18 seconds end to end (3.84 MiB/s). Dedicated Drive
to the same Colab VM via `rclone copyto` took 12.58 seconds on the VM
(40.70 MiB/s; 16.54 seconds including SSH command setup). Both copies matched
the local MD5 `1e9352d9aaa5d2e33b39593fbccc7466`. A separate 32 MiB
compressed rclone binary was uploaded for the benchmark; that setup time is
not included in either file-transfer timing. The WSL test ran while the Qwen
model upload to Drive was still active, so the measured local path shares
uplink capacity and is not its idle-bandwidth maximum. The CPU runtime showed
0.08 CU/hour and was stopped after the comparison; `colab usage` then showed
zero assignments and 0.00 CU/hour. This is one-part evidence, not a 38.79 GiB
restore benchmark.

## Portability decision and remaining gates

The stage-2 U02 telemetry protocol and report schema are in
`2026-09-24-colab-u02-measurement.md`. The completed second-runtime
measurements and verified U02 continuity result are in
`2026-09-24-colab-u02-results.md`.

Directly booting the provider-specific image on a managed Colab runtime is
not an available restore path. Restore the application source and model files,
then rebuild dependencies against the allocated Colab GPU/runtime. The
existing `gpu_profile=auto` maps unknown GPUs (including A100) to the
`rtx4080` bypass-attention profile; this avoids the 5090 SageAttention patch
but is not proof of H3 generation parity. The rental SageAttention extension
was compiled for `sm_120a`, while A100 is `sm_80`; it cannot be reused as-is.
ComfyUI disables native NVFP4 compute below capability 10 and uses emulated
operations. The A100 completed text encoding and one H3 sample on that path,
but the 18:34 sample time is not a measured 5090 throughput comparison.

Gate status after the second A100 run:

1. **Passed:** six selected models (38.79 GiB) uploaded and hash-checked on
   Drive, then restored on a fresh A100 runtime. Full restore was 912.129 s;
   detailed timing and CU caveats are in the result document.
2. **Passed for one sample:** second-runtime dependency rebuild and
   U01-to-U02 `motion_latent` continuation through the repository
   `run_ep_units_profiled.py` CLI loop. U02 returned `success`, with a new
   MP4 and AV latent. The stage-1 one-off bound workflow had not exercised
   this full CLI loop. Do not treat different U01/U02 units as a controlled
   throughput A/B.
3. **Pending:** evaluate visual/audio quality across more than one sample and compare
   elapsed time against the rental RTX 5090 before calling A100 a full
   replacement.

Colab runtimes are ephemeral and GPU allocation is not guaranteed. Retain the
D: backup and a scripted rebuild path rather than treating the live Colab VM
as the only restore point.

## Backlog (next work, not part of the measured U02 gate)

- **SM80 offline optimization stopped 2026-09-26:** the active graph invokes
  the A100 SageAttention kernel. The archived target uses 255 registers/thread;
  the sole `launch_bounds` candidate reduced this to 168 but raised its stack
  frame from 32 B to 872 B and greatly increased compile-time spills. Both
  wheels and resource evidence are archived on D; no runtime slowdown or
  quality change is claimed. The predeclared build gate rejected this
  candidate, so do not start another A100 run for it. See
  `2026-09-26-h3-a100-sm80-phase-a-result.md`. Astra PASSed the next
  **zero-CU decision plan** in `2026-09-26-h3-post-sm80-decision-plan-for-astra.md`:
  first search existing 5090 evidence, then consider at most one matched-input
  screen during an already needed rental window. It authorizes no GPU run or
  migration. The older paid A100 Gate 1 remains disabled; its trace-causality
  blockers are documented in `2026-09-26-h3-a100-gate1-run-contract.md`.
  Offline inventory in `2026-09-26-h3-post-sm80-gate0-inventory.md` found
  historical 5090 U02 runs, but their parent latents do not match the frozen
  A100 U01 parent and no correlated server/sampler receipt exists. Mark the
  old 646-656 s client observation `INCOMPARABLE`; do not rent a 5090 solely
  to fill this gap. The media timeline fixture is implemented and tested;
  a cross-environment receipt/runbook still needs a rental-window check.
  Zero-CU tooling and its remaining provenance boundary are recorded in
  `2026-09-26-h3-gate0-implementation-result.md`; this is not a 5090 run or
  permission to start one. Astra PASSed the next **A2 zero-CU provenance
  plan** in `2026-09-26-h3-gate0-provenance-closeout-plan-for-astra.md`:
  prefer existing prompt-bound WebSocket progress over attributing shared
  logs, bind outputs to history, and downgrade incomplete evidence rather
  than rerun. The plan is not yet implemented and does not authorize Stage B.
- **Deferred by operator on 2026-09-25:** complete blinded human review of the
  formal A100 bypass/Sage U02 pair, including continuous picture and sound,
  first/last-second seam, identity/clothing, prop/contact, flicker, dialogue,
  lip sync and clipping. An agent's 0.25-second-frame visual review found only
  a weak preference and could not hear audio; it is not quality sign-off.
  Keep the `review/clip-A.mp4`/`clip-B.mp4` mapping withheld until the human
  review is submitted. Do not promote the candidate or pay for U03 continuation
  while this gate is deferred. Evidence: `2026-09-25-h3-a100-ab-results.md`.
- **Performance investigation completed 2026-09-26:** one A100 session ran
  P_B/P_C/M0 one-step profiles, then full U02 S1/M1 with only the
  `--disable-smart-memory` flag changed. M1 produced the same decoded video,
  audio and exact AV latent as S1 but improved server time only 0.16%, sampler
  time 0%, and raised sampled VRAM peak from 35,910 to 51,396 MiB. The
  predeclared >=15% gate failed, so S2/M2 were not run. Keep the current Sage
  startup policy; do not escalate to `--highvram` based on unused capacity
  alone. Full evidence and accounting:
  `2026-09-26-h3-a100-combined-results.md`.
- **Before another paid batch:** fix raw MP4 equality: labeled S1/M1 files
  differ only in embedded output-name metadata, while decoded video/audio
  hashes match. Compare normalized media essence rather than raw container
  bytes. Also poll terminal Drive receipts while `colab exec` is silent; M1
  finished/archived at 10:09 UTC but the CLI did not return until transport
  loss about 21 minutes later, increasing CU consumption. Preserve the
  stop-without-blind-retry rule and separately authorize any future paid run.
- **Before an unattended paid batch:** make Colab CLI phase calls bounded and
  reconcile remote receipts after transport loss; never blindly retry an
  uncertain prompt. The formal A/B completed only after manual recovery from
  a CLI connection loss in the same VM. This is an operations reliability
  task, not a measured inference speedup.
- A100 80GB H3 quality/throughput research is archived in
  `2026-09-24-h3-a100-optimization-research.md`. Discuss and prioritize its
  experiments now that the unchanged U02 continuity gate passed. No model,
  sampler, reference sizing, attention, or startup-flag changes were part of
  that measured gate.
- Provide a one-command restore for each new Colab Pro runtime: fetch the
  selected source/models and parent latent from Drive, verify hashes, rebuild
  compatible dependencies, start the team ComfyUI, and run readiness/node
  checks. Record restore time and CU usage; fail fast and release the runtime
  on error. This automates recovery, not booting a persistent/custom image.
- Run consecutive U units in one Colab runtime to avoid repeated model restore.
  Keep each parent AV latent on the VM for the next `motion_latent` unit, and
  incrementally copy each successful unit's MP4, latent, and run metadata to
  Drive with size/hash verification. Do not wait until the end for the first
  backup or write ComfyUI output directly to a Drive mount.
- After the full chain succeeds, optionally assemble a Drive-side delivery
  bundle. Measure whether bundling saves time before adding compression or
  another full local copy; it is not required for the U02 portability gate.
- H3 quality research: the current Ref2VA workflow is a working H3-Base
  deployment, not the complete three-module H3 system. It uses a community
  hybrid int8 DiT, NVFP4 Qwen encoder, int8 video VAE, and two LoRAs; the
  optional local latent-upscale pass is not MiniMax H3-Regenerate-2K. MiniMax
  has not released the H3-Context-IR or H3-Regenerate-2K modules for local
  deployment. Keep these distinctions explicit in future evaluations.
  Source: https://github.com/MiniMax-AI/MiniMax-H3/blob/main/README.zh-CN.md
- After the unchanged U02 continuity gate, run controlled short-clip quality
  A/B tests, changing one variable at a time: reference-to-prompt mapping and
  full shot timeline; Turbo LoRA/scheduler/step compatibility; the second
  style LoRA; `ref_image_size=max` versus `match`; and quantized versus FP16
  video VAE. Score identity, spatial/temporal continuity, dialogue/audio,
  artifacts, wall time, and CU. Do not treat a faster GPU as a quality fix.
- Establish an official BF16 Ref2VA H3-Base baseline before claiming the
  community hybrid is better or worse. FL2VA is a separate checkpoint needed
  only for text/first-last-frame use cases. A single 80 GB GPU requires
  offloading the approximately 61.7 GB DiT and 62.1 GB conditioner; verify
  host RAM, storage, restore time, and actual Colab feasibility before any
  large download or GPU allocation.
  Source: https://huggingface.co/docs/diffusers/main/en/api/pipelines/minimax_h3
- If the target is official end-to-end 2K H3 rather than a local upscale,
  evaluate MiniMax Context-IR and Regenerate-2K APIs around a local H3-Base.
  For maximum local throughput, assess persistent multi-GPU H100/H200-class
  serving separately from Colab Pro; Colab hardware and lifetime are not
  guaranteed. Defer spending and deployment decisions until quality and
  end-to-end cost comparisons are measured.
- Hugging Face follow-up: download only the selected task family and file
  format, never the entire `MiniMaxAI/MiniMax-H3` (498 GB) or
  `Comfy-Org/MiniMax-H3` (485 GB) repository. The original `Ref2VA/` folder is
  about 144 GB; the ComfyUI single-file Ref2VA DiT choices are 66.3 GB BF16,
  34 GB int8-convrot, or 21 GB pruned int8-convrot. Qwen choices include
  51.5 GB BF16, 27.1 GB int8-convrot, or 15.7 GB NVFP4-AWQ. The Comfy-Org
  card explicitly says its NVFP4 text encoder works without Blackwell and
  prefers int8-convrot DiT with cu130. These are file sizes, not peak VRAM.
  Sources: https://huggingface.co/MiniMaxAI/MiniMax-H3/tree/main/Ref2VA
  https://huggingface.co/Comfy-Org/MiniMax-H3/tree/main/diffusion_models
  https://huggingface.co/Comfy-Org/MiniMax-H3/tree/main/text_encoders
- The lowest-transfer checkpoint comparison is the current b25-49 hybrid
  versus Comfy-Org's native pruned int8-convrot Ref2VA DiT (both about 21 GB),
  with the same references, prompt, encoder, VAE, LoRAs, sampler, and seed.
  This isolates the hybrid merge more cleanly than jumping straight to BF16;
  only then consider separate no-LoRA and BF16 baselines. The hybrid author's
  claimed fidelity/reference tradeoff is not an acceptance result for EP04.
  Source: https://huggingface.co/smhfacct/Minimax-H3-fl2va-ref2va-hybrid-models/blob/main/README.md
- For future Ref2VA speed A/B, evaluate variant-matched adapters rather than
  assuming the current Turbo v4 is validated on the hybrid checkpoint.
  Hugging Face lists a dedicated Ref2VA 4-step Turbo and an Alibaba-PAI
  Ref2VA 8-step PDD adapter. PDD requires matching official transformer
  weights plus its preparation/fusion process; neither is an untested drop-in
  replacement for the current hybrid graph. Preserve the original workflow
  and avoid downloads until the U02 gate and a short-clip test plan are ready.
  Sources: https://huggingface.co/Comfy-Org/MiniMax-H3/tree/main/loras
  https://huggingface.co/alibaba-pai/MiniMax-H3-Acc-LoRAs
- A community Ref2VA NVFP4 DiT claims a Blackwell-specific speed gain, but
  its native FP4 path requires SM120 and its benchmark is author-reported on
  RTX PRO 6000, not the Colab A100. Treat it as a later rental/Blackwell
  experiment, not an A100 optimization or established quality improvement.
  Source: https://huggingface.co/ModelsLab/MiniMax-H3-ref2va-NVFP4
