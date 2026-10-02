# Colab A100 U02 portability gate: measured result (2026-09-24)

## Outcome and evidence boundary

EP04 manual-v16 U02 completed on a **new** Colab Pro A100 High-RAM runtime,
using the original one-pass `motion_latent` workflow and U01 AV latent. The
ComfyUI prompt returned `success`, the client returned exit 0, and both an MP4
and the successor AV latent were saved. The model restore and software rebuild
therefore worked on a second runtime, not only on the original U01 VM.

This proves technical U01-to-U02 latent continuity and output creation. It
does **not** establish visual/audio acceptance for a full episode, equivalence
to the rental RTX 5090, repeated-run reliability, or a one-command restore.
The U02 contact sheet was inspected for obvious content, but no frame-by-frame
quality or identity score has been signed off.

The independent local evidence is under
`D:\comfyui-h3-backups\rental-20260924-5090\colab-stage2`. The 49,039,360-byte
`h3-u02-evidence.tar` contains `h3-u02-results/` and `h3-u02-metrics/` and
has SHA-256
`13cba9cd95420a7b5dc56b2efb78838fe62c6da3dbf2fa7a5816320397cbd706`.
The same archive is at the dedicated Drive prefix's `stage2/` directory;
Drive MD5 and the downloaded D: SHA-256 matched the Colab source. The D:
archive is also extracted under `colab-stage2/evidence/`. The Drive backup
receipt records archive/hash/upload/remote-check subphase times.
The exact tested restore/setup/run wrappers, telemetry/backup scripts and
compressed rclone binary are separately preserved under
`colab-stage2/control-scripts/`; all seven entries passed `SHA256SUMS` local
readback. OAuth configuration and tokens were deliberately not copied there.

## Runtime and workload

| Item | Observed value |
| --- | --- |
| Assignment | `h3-u02-20260924`, A100 High-RAM, one active assignment |
| GPU | NVIDIA A100-SXM4-80GB, 80 GiB physical VRAM, SM 8.0 |
| Driver | 580.82.07 |
| VM | Linux 6.6.122+, 12 vCPU Intel Xeon @ 2.20 GHz, 179,370,467,328 B RAM, no swap |
| Disk | `/content` overlay 253,055,008,768 B total; 202,131,714,048 B free in base snapshot, 151,393,734,656 B free after restore/setup |
| Base Python/Torch | Python 3.13.15, PyTorch 2.11.0+cu128, CUDA 12.8 |
| Rebuilt Python/Torch | Python 3.13.15, PyTorch 2.14.0+cu130, CUDA 13.0, cuDNN 92400 |
| ComfyUI | 0.34.0; frontend 1.51.10; 23/23 required workflow classes registered |
| Startup flags | `--lowvram --reserve-vram 4 --disable-smart-memory --force-fp16 --disable-cuda-graphs --enable-manager`; localhost port 8188 |
| Workflow | EP04 manual-v16 U02, `motion_latent`, one pass, no second pass, `gpu_profile=auto` -> `rtx4080(bypass)` |
| Models | Six selected files, 41,651,185,023 B / 38.79 GiB; three large files as 76 x <=512 MiB Drive parts, three direct files |
| Parent | U01 AV latent `h3_context/ep04_u01_00001.safetensors`, MD5 `1fb13e523c23b48b0b9480b18016f91a` |

The source archive and runner archive used by this VM have local SHA-256
`db6e20a71fe6ac87c7a4a981f08ae0685db7c0229d3db5bdd5b51f0832ab1fc7`
and `8ac917e997722abcb5b11a6f1068a260fdc2dc092b243075d524dadb151b1f5a`,
respectively. The source archive has no `.git` directory, so a ComfyUI Git
commit could not be recovered from the VM; the live `/system_stats` version
and archive hash are the applicable provenance.

An optional `ComfyUI_NVIDIA_RTX_Nodes` import failed for missing `nvvfx`, and
GoohaiTools logged a missing optional `mediapipe` package. Blank image-loader
nodes also emitted input-directory warnings. None is required by the 23
classes in this workflow; the prompt completed. Do not misreport these
warnings as a clean startup or as a U02 failure.

## Timeline and effective transfer rates

UTC times are retained in the raw JSONL records. PDT is UTC-7 on this date.

| Phase | UTC boundary | Wall time | Notes |
| --- | --- | ---: | --- |
| Active assignment observed | 17:58:05 to 18:52:32 | about 54m 28s | Snapshot bracket, not provider-internal billing timestamps |
| Base environment snapshot | 18:00:07 | - | Before restore; no GPU work |
| Drive -> Colab restore | 18:00:28 to 18:15:40 | 912.129 s / 15m 12s | Source, runner, six models, hashes, parent latent |
| Model subset within restore | 18:00:42 to 18:15:35 | 893.54 s / 14m 54s | 41,651,185,023 B; **44.45 MiB/s effective** |
| Dependency install + ComfyUI ready | 18:17:23 to 18:18:33 | 70.126 s | `uv` rebuild, process start, readiness poll |
| Node-class preflight | 18:21:10 | - | 23 required, zero missing |
| U02 client wrapper | 18:21:41 to 18:47:50 | 1569.103 s / 26m 09s | Queue, server wait, output downloads |
| ComfyUI execution history | 18:21:41.805 to 18:47:46.788 | 1564.983 s / 26m 05s | Server reports `Prompt executed in 00:26:05` |
| Backup archive/upload/verify | 18:51:18 to 18:51:26 | 8.385 s | 49,039,360 B, Drive MD5 matched |
| Local archive download | after Drive verification | about 11 s CLI wall | D: SHA-256 matched; separate CLI transfer |

The roughly 11.9 minutes outside the restore/setup/U02 measured phases
include session creation, script uploads, preflight and result capture,
orchestration waits, backup and stop. It is not all unproductive idle time,
but it is charged while the A100 assignment is active and is a target for
future one-command automation.

Large-model Drive -> Colab effective rates below include download, disk
write, reassembly and SHA-256. They are not isolated network bandwidth:

| Model | Bytes | Timed boundary | Effective rate |
| --- | ---: | ---: | ---: |
| Video VAE | 3,171,670,912 | 74.395 s / 6 parts | 40.66 MiB/s |
| Qwen3VL encoder | 15,687,142,551 | 344.700 s / 30 parts | 43.40 MiB/s |
| Hybrid UNet | 20,970,379,632 | 462.454 s / 40 parts | 43.25 MiB/s |
| All six selected models | 41,651,185,023 | 893.54 s | 44.45 MiB/s |

The dedicated-client WSL D: -> Drive upload used a separate network path
and **no Colab VM/CU**. Its rclone log boundaries include retries/stalls and
chunk commits; effective rates are not peak speed:

| Object | Local-to-Drive wall time | Effective rate | Remote check |
| --- | ---: | ---: | --- |
| Video VAE, 6 parts | 586 s | 5.16 MiB/s | 6 matches, zero differences |
| Qwen3VL, 30 parts | 3162 s | 4.73 MiB/s | 30 matches, zero differences |
| UNet, 40 parts | 4729 s | 4.23 MiB/s | 40 matches, zero differences |
| Audio VAE | 431 s | 1.34 MiB/s | Match; first 64 MiB stalled for about five minutes |
| MysticXXX LoRA | 117 s | 4.86 MiB/s | Match |
| Turbo v4 LoRA | 124 s | 4.77 MiB/s | Match |

The dedicated upload log spans 08:13:35-10:54:35 PDT to `UPLOAD_READY`
(2h 41m including checks and inter-file gaps). The UNet's last few parts
slowed sharply but completed without a recorded 403; the audio VAE's first
64 MiB stalled and then resumed. Preserve these as variance, not as a stable
5 MiB/s guarantee. Restore had no recorded model mismatch or retry failure.

## U02 execution and output

- Prompt ID: `bc13f625-3098-4898-bd51-e36184b820c4`; job ID:
  `bfa066ba56a5`; history status: `success`; prompt audit:
  `preflight_ok=true`, zero semantic/wiring violations.
- The ComfyUI log explicitly records loading the U01 AV latent, passing H3
  layout checks, and saving successor
  `h3_context/ep04_u02_00002.safetensors`. It logs 22 parent video frames
  mapped to 7 conditioning blocks, a 328-frame pre-trim clip, 22 trimmed
  frames, and 306 delivered frames. Picture and sound both end at 12.7500 s;
  logged drift is 0.00 ms.
- Sampler progress: 12/12 steps, 24m 07s from the progress meter. Steps after
  initial model preparation were mostly about 122 s. The approximately 1m
  58s difference from full server execution includes other nodes/decode/save;
  no reliable per-node boundary was recorded, so it must not be assigned to
  a specific component.
- MP4: `EP04-U02-v16-pass1_00001-audio.mp4`, 9,952,904 B, SHA-256
  `b31d5b02ae72114a69f9a4524d47c5d68134b1b6c2efa7c2bc1921e63af3d5ff`.
  `ffprobe` reports 12.75 s, 768x1376 at 24 fps, H.264 video and AAC stereo
  audio at 32 kHz. Audio is non-silent (`volumedetect` mean -15.5 dBFS,
  peak about 0 dBFS); this is a signal check, not listening acceptance.
- AV latent: `ep04_u02_00002.safetensors`, 38,580,184 B, SHA-256
  `2b7dbee29f95ae0e2179b89f3ae0cc64e3b52b7623cada0225828a9a55edcf1a`.
- Extracted MP4/latent hashes on D: match the capture manifest. A contact
  sheet is at `colab-stage2/u02-contact-sheet.png` for visual review.

U01's earlier 18m 34s server execution was a different chain-start unit.
U02 has parent-latent conditioning and a different frame workload, so the
26m 05s vs 18m 34s delta is **not** a controlled GPU-speed comparison.

## Resource utilization and CU

The telemetry runner sampled `nvidia-smi`, host memory and disk every five
seconds. There were 182 restore, 14 setup and 312 U02 samples. These are
instantaneous samples, not continuous maxima or a kernel profiler:

| Phase | GPU utilization mean / max | Sampled VRAM peak | Power mean / peak | Temperature peak |
| --- | ---: | ---: | ---: | ---: |
| Restore | 0% / 0% | 0 MiB | 52.5 / 53.0 W | 33 C |
| Setup | 0% / 0% | 428 MiB | 54.6 / 58.5 W | 33 C |
| U02 | 96.5% / 100% | 35,566 MiB / 34.7 GiB | 382.0 / 494.7 W | 68 C |

During U02, minimum sampled host `MemAvailable` was 138.79 GiB and minimum
free disk was 140.93 GiB. This run used considerably less than 80 GiB GPU
VRAM but kept the GPU busy; the readings alone do not prove that VRAM
offloading is the root of the U02 step time.

`colab usage` reported **6.77 CU/hour** for this A100 High-RAM assignment,
including restore and waiting while the VM was active. Selected snapshots:

| Boundary (UTC) | Balance | Active / rate |
| --- | ---: | --- |
| Before assignment, 17:57:40 | 185.41 CU | 0 / 0.00 CU/hour |
| Assigned, 17:58:05 | 185.41 CU | 1 / 6.77 CU/hour |
| Restore done, 18:17:03 | 183.42 CU | 1 / 6.77 CU/hour |
| Just before U02, 18:21:32 | 182.85 CU | 1 / 6.77 CU/hour |
| U02 done, 18:49:16 | 180.03 CU | 1 / 6.77 CU/hour |
| Artifacts safe, 18:52:11 | 179.46 CU | 1 / 6.77 CU/hour |
| Stopped, 18:52:32; rechecked 18:54 | 179.46 CU | 0 / 0.00 CU/hour |

The observed whole-stage balance drop is **5.95 CU**. At the displayed
6.77 CU/hour, rate-times-wall estimates are 1.72 CU for restore, 0.13 CU
for setup, 2.95 CU for the U02 wrapper, and about 6.15 CU for the entire
observed active window. The rate calculation and 5.95-CU balance delta do
not match exactly; balance updates/rounding and the bracketing of actual
assignment time prevent an exact per-phase billed CU allocation. Do not call
the U02 pre/post balance difference an exact single-prompt price. The
authoritative evidence is the raw `cu-snapshots.jsonl` plus phase wall times.

## Next decision

The portability gate is green for **one clean-runtime rebuild plus U02
motion-latent continuation**. Keep the VM stopped. Before broad migration,
review U01/U02 audiovisual continuity and repeatability, and compare an
equivalent workload/cost with the rental 5090. A one-command restore and
consecutive-U execution can remove much of the 11.9-minute non-core active
window and avoid repeated 15-minute model restores; those remain backlog
work, not changes to this measured run.
