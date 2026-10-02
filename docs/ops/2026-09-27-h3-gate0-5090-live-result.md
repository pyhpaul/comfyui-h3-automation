# H3 Gate 0 RTX 5090 live U02 result (2026-09-27 UTC)

## Decision

One authorized EP04-U02-v16 prompt was submitted once on the live rental RTX 5090.
The integrated source-side evaluator returned `deployment_combination_screen`.
This is a same-frozen-input deployment-combination timing screen, not a
hardware-only benchmark or a visual-quality acceptance.

The 105-minute authorization was a maximum wall window, not an exclusive GPU
reservation. The actual measured prompt ran from 05:06:18.902 to
05:16:44.308 UTC (625.406 s). The queue was checked empty before submission,
contained only this prompt during execution, and was empty at 05:17:34 UTC.
Production work could coexist during setup and can resume after the measured
segment; concurrent ComfyUI/GPU work during the segment would invalidate the
isolated timing interpretation.

## Source-side evidence

- Run ID: `gate0-5090-20260927-01`; prompt ID:
  `9ae8e0aa-1c5e-4465-a05e-655eef9e3198`.
- Frozen manifest SHA-256:
  `9a5f0d43b7e93a0fc5a3226c1970f79e88db03550cfc57dbbdcb502c5beb4609`.
  Candidate graph SHA-256:
  `a81fc8480927c4c6a3632b3950c1815ba12ea01c58896b8090ddf702d2f9b983`.
  A100 U01 parent SHA-256:
  `6def89c01d367a64be354a93dfb7e96806d236211eb0fdfcbf4bfe493a95946a`.
- The frozen references were staged under a run-specific input alias; the live
  production input files with colliding basenames were not overwritten.
  Candidate normalization and source-side SHA-256 checks passed for graph,
  parent, four references, six models and source files. The post-run evaluator
  re-read the referenced bytes. Loader-side byte hashes were not captured,
  so before/after file hashes do not prove the exact bytes read by the node.
- Runtime: NVIDIA GeForce RTX 5090, 32,607 MiB GPU memory, compute capability
  12.0, driver 610.43.02; ComfyUI 0.34.0, Python 3.12.3, Torch
  2.14.0+cu130, CUDA 13.0. The existing production ComfyUI process (PID 3995)
  was not restarted. Its startup flags included `--lowvram`,
  `--reserve-vram 4`, `--disable-smart-memory`, `--force-fp16`, and
  `--disable-cuda-graphs`.
- History reported success, sampler node 226 was not cached, and the prompt-
  bound WebSocket observer recorded all 12 ordered sampler progress steps.
  The observer-receive node interval was 534.212 s; this is not an execution
  sampler-wall clock. The source log reported `Prompt executed in 00:10:25`.
- GPU telemetry was captured every 5 s. The prompt-window subset contains
  127 samples and passed GPU UUID, PID, cadence and edge-coverage checks.
  Sensor utilization/VRAM readings remain reported-only.
- Source media: `video_00001-audio.mp4`, 9,947,730 bytes, SHA-256
  `4208ba6f889be53f6ca79806c860233691b9d7c0a6b8e3759b9aab2c1403b657`;
  306 frames, 24 fps, 12.75 s picture, AAC 32 kHz stereo. The paired
  `latent_00002.safetensors` is 38,580,184 bytes, SHA-256
  `22959a2a722ec02cb0f2da2d7a1f12153543f0d964d5d3e08488d90f589c9578`.
  The reviewed C1 audio-contract addendum matched. The D: backup hashes match
  the source-side evaluator.

## Comparison boundary

Archived A100 C1 server wall was 1324.348 s. This 5090 run was 625.406 s,
about 2.12x faster or 52.8% less server wall. The comparison covers the
deployed ComfyUI/model/attention/memory combination and permitted path/profile
deltas, not GPU silicon alone. A100 C1 lacks a prompt-bound WebSocket trace,
so no cross-device sampler-wall ratio is claimed. No human blind review of the
5090 MP4 has been completed; timing and structural media checks do not prove
visual or audio quality parity.

## Archive and replay

Local D: archive:
`/mnt/d/comfyui-h3-backups/rental-20260924-5090/a100-perf-pilot/gate0-5090-20260927-01/`.
It contains `evaluation.json`, the MP4 and latent, `submitted_graph.json`,
and `source-evidence/` with history, handoff, trace, raw/window GPU JSONL,
environment, queue snapshot, log slice, baselines, manifest, reference graph,
and the approved audio addendum. Source run evidence remains under
`/tmp/h3-gate0-5090-20260927/run/gate0-5090-20260927-01/` while that
instance exists. No second `/prompt` submission or automatic retry occurred.

Focused regression after the reference-alias and telemetry changes:
`76 passed` across the four touched Gate 0 test modules. The live evaluator
returned `deployment_combination_screen`; its environment and GPU sensors are
still explicitly lower-tier self-reported observations.
