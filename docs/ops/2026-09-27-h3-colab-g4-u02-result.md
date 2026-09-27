# Colab G4 single-U02 result (2026-09-27 UTC)

## Decision

One EP04-U02-v16 `motion_latent` prompt completed on a Colab G4 assignment.
The 12.75-second H.264/AAC MP4 and AV latent were validated and archived to
Google Drive. The generated graph matched the archived A100 C1 graph except
for output filename prefixes. This is a single deployment-combination timing
observation, not a GPU-only benchmark or final audiovisual acceptance.

Two orchestration defects were exposed and must not be hidden:

1. The reused A100 preflight expected the newer repository `gpu_adapt.py` SHA,
   but the frozen Drive runner archive contained the older SHA. It raised an
   exception. `colab exec` returned process status zero anyway, and the G4
   phase checked only that `preflight.json` existed. Thus the prompt ran despite
   a failed preflight. All six models, four image inputs, prompt source,
   KJNodes source, and U01 parent matched; the actual submitted graph matched
   C1. This narrows but does not erase the provenance exception.
2. Remote generation and Drive publication succeeded, but the host's 5-second
   receipt read timed out. The host exited 1 after safely stopping the session.
   A subsequent direct read confirmed the identity-bound terminal receipt had
   `state=success` and `archive_state=verified`. Do not call the original host
   command an end-to-end automation success.

The G4 scripts were subsequently changed to require stage success markers,
verify every preflight asset on the host and again in the phase, recognize the
reviewed Drive runner SHA, and reconcile a slow receipt read. These changes
are code-checked only; no second paid G4 run was authorized or performed.

## Exact run and hardware

- Session: `h3-g4-u02-20260927-064924`
- Prompt: `c9bad5d7-2275-487a-8865-735d92f25833`
- Assignment: NVIDIA RTX PRO 6000 Blackwell Server Edition, compute capability
  12.0, 101,974,081,536 bytes VRAM (97,887 MiB reported by `nvidia-smi`),
  driver 580.82.07. The initial image had Torch 2.11.0+cu128; the installed
  H3 venv used Python 3.13.15, Torch 2.14.0+cu130 and a locally built
  SageAttention 2.2.0 SM120 wheel.
- Wheel SHA-256: `1cdc658e69315ce4cd7d18d91d55dba42466261607e024ebec17b25c7c4ffbe9`
- ComfyUI startup flags were the archived `comfy_gpu_start.sh`: `--lowvram`,
  `--reserve-vram 4`, `--disable-smart-memory`, `--force-fp16`,
  `--disable-cuda-graphs`. The `rtx5090` profile was selected explicitly on
  G4 to retain `MiniMaxH3MemoryEfficientSageAttentionPatch`; `auto` would have
  selected the bypass profile for an unknown device name.
- Exactly one prompt appeared in history; `execution_cached.nodes=[]` and the
  Comfy log contains 12 ordered sampler steps and the Sage patch application.

## Timing, transfer and compute units

| Item | Observed |
| --- | ---: |
| Assignment CU rate | 8.90 CU/hour |
| Host command wall (includes pre-assignment and post-stop work) | 1,488.01 s |
| Assigned-to-after-stop snapshot bracket | 1,402 s |
| Torch preinstall host stage | 24.25 s |
| Drive restore host stage | 627.11 s |
| Model restore within script | 606.46 s |
| Full restore within script | 619.67 s |
| Runtime setup host stage | 31.40 s |
| Preflight host stage (failed but was not caught) | 32.51 s |
| Comfy history server wall | 520.258 s |
| Log sampler wall | 479 s |
| Remote phase wall, including process startup and validation | 541.11 s |

The six models total 41,651,185,023 bytes (38.79 GiB), equivalent to about
68.7 MB/s over the 606.46-second model restore. The total restore also pulled
the 420 MiB source archive, 9.7 MiB runner archive and 34.6 MB U01 parent
latent. These are aggregate stage rates, not a benchmark of one network link.

The first balance snapshot was 148.18 CU; the post-stop snapshot was 145.22 CU,
an observed balance difference of 2.96 CU. Balance settlement may lag wall
time, so this is not a final invoice. At the displayed 8.90 CU/hour, the
1,402-second assigned-to-after-stop bracket implies about 3.47 CU; its
snapshot endpoints are not exact charge timestamps. The 627.11-second restore
stage corresponds to about 1.55 CU, and the 541.11-second generation phase to
about 1.34 CU at that same displayed rate. These are estimates, not separate
billed line items. The safety watchdog deadline was four
hours, but no CU cap was imposed. `stop.log`, `sessions-after-stop.log` and
`colab usage` confirmed zero active assignments and 0.00 CU/hour after stop.

GPU telemetry sampled 107 times at approximately five-second intervals:
mean utilization 94.4%, peak VRAM 35,807 MiB, mean power 573.2 W, peak
power 607.98 W, mean SM clock 2,266 MHz, maximum temperature 80 C. These are
sensor readings, not a direct proof of model memory residency.

## Artifact validation and comparison

- MP4: 9,931,303 bytes; SHA-256
  `871a7478f2a0a041743403eb84a0c3804c2ec4f5f4d66335a36f86b87cd71c10`.
  Full decode and media checks passed: H.264 768x1376, 24 fps, 306 frames,
  12.750 s, AAC 32 kHz stereo with 12.736 s audio duration. The decoded
  video/audio hashes match `run/validation.json`.
- Latent: 38,580,184 bytes; archived validation reports SHA-256
  `fe7bba15b43bcaee71ddc2b0d6e22681bae841842e351a9eccbdf9f543fcb992`,
  expected two F32 finite tensors and expected shapes. The local evidence pull
  excluded the latent file, so this hash was not independently recomputed
  after publication; `publish_verified` did run `rclone check` remotely.
- Drive output root:
  `h3drive_h3:comfyui-h3-colab-dedicated/rental-20260924-5090/g4-u02/h3-g4-u02-20260927-064924/G4_U02`.
- Local MP4 copy and logs:
  `/mnt/d/comfyui-h3-backups/rental-20260924-5090/g4-u02/h3-g4-u02-20260927-064924/`.
- The G4 server wall was 16.8% less than the single RTX 5090 U02 sample
  (625.406 s) and 60.7% less than A100 C1 (1,324.348 s). Different runtime
  builds, startup states, attention kernels and the single-sample design limit
  causal and repeatability claims.
- A blinded 4-fps frame sample of the G4 and 5090 clips found them highly
  similar and weakly preferred the G4 clip, with low confidence. It did not
  include continuous playback or audio listening. Final audiovisual quality
  acceptance remains with the operator.

## Provenance and next gate

The archived runner's `gpu_adapt.py` SHA-256 is
`a2333220eafb3a90d333312883a5e1875a5b95cf991e994e0ec27bf8bfa4efaa`;
the current repository copy is
`138218e54c2df112b88eea10035faf564fd8111ef6cc79ecdd8c2ae53a4cb2bf`.
The source diff adds the experimental A100 profile; the existing `rtx5090`
attention branch remains the same. The G4 run used that `rtx5090` branch, and
the submitted graph was compared node-for-node with C1 before queueing.

Before another paid run, execute the amended host dry-run and targeted tests;
then require a fresh valid `PREFLIGHT_OK` and all-true JSON report before any
prompt. This run already meets the requested one-U02 output criterion; no
automatic repeat is justified merely to repair the orchestration receipt.

Post-run offline verification: `python3 -m compileall` passed for the changed
scripts; `.venv/bin/pytest -q tests/test_h3_g4_u02_host.py
tests/test_h3_a100_ab_contract.py` passed 21 tests; the amended host dry-run
reported `paid_started=false`. None of these retroactively validates the
original failed runtime preflight. An independent Astra evidence review agreed
that the U02 output and archive succeeded, while full frozen admission and
strict quality/performance acceptance did not.
