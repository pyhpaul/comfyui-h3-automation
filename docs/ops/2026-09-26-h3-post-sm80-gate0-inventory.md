# Post-SM80 Gate 0: offline evidence inventory

Status: **existing 5090 runs are INCOMPARABLE to the formal A100 U02**.
This is an archival screen, not a new benchmark. No GPU session, CU,
model transfer, rental restart, prompt submission, or blind-map access was
used for this inventory.

## Existing 5090 evidence

| Evidence | What it proves | Why it cannot be the matched baseline |
| --- | --- | --- |
| `runs/ep04_manual_v16_u01_u09_motion_latent.json` and `.log` | EP04-U02-v16 completed on RTX 5090 using `minimax_sage_fp8`, prompt `37ae4301-13b4-4be6-947d-71c63f999e2b`; client polling reached 646 s before success | Parent was `h3_context/ep02_u01_00001.safetensors`, not the A100 U01 parent; no correlated server/sampler/12-step receipt or preserved submitted graph |
| `runs/ep04_manual_v19_u01_u02.json` | A later 5090 U02 completed with a different v19 job and prompt | Different job/prompt and different parent latent; no matched server timing |
| `output.tar` in the D: rental archive | Contains the v16 parent/child latents and v19 parent/child latents | Does not contain a matching A100-parent 5090 U02 sample |
| `runtime.tar` in the D: rental archive | Contains `ComfyUI/user/comfyui.db` and an older `h3-motioncontext-restart.log` | SQLite has asset tables, not execution history. The log was last modified 2026-09-10 and has no matching U02 prompt ID; its unrelated `Prompt executed in` lines cannot be assigned to this run |

The decisive parent-byte check, performed by streaming individual files from
`output.tar` without restoring the runtime:

| Parent latent | SHA-256 / MD5 | Provenance |
| --- | --- | --- |
| A100 formal U02: D: `colab-stage1/ep04_u01_00001.safetensors` | SHA-256 `6def89c01d367a64be354a93dfb7e96806d236211eb0fdfcbf4bfe493a95946a`; MD5 `1fb13e523c23b48b0b9480b18016f91a` | Colab-generated EP04-U01-v16; formal preflight confirmed MD5 |
| 5090 v16 U02 parent: `output/h3_context/ep02_u01_00001.safetensors` | SHA-256 `9131bac0d54ed957890fe7e24411bfc329bb6e86ac4add6608fc3915ce249376`; MD5 `cf3c3d23ef7fe75e2e4cf0e11e624cdc` | `runs/ep04_manual_v16_u01_u09_motion_latent.json` parent path |
| 5090 v19 U02 parent: `output/h3_context/ep04_u01_00001.safetensors` | SHA-256 `414623d723c99305a61a21df9dce6a8e9fbe2990bd70108c8e9dff3f38a6562e`; MD5 `3c2959ad230efbaf630e678edc0b1f06` | `runs/ep04_manual_v19_u01_u02.json` parent path |

Thus the historical 646-656 s 5090 client observation remains directional
only. Matching the v16 job name is insufficient when the motion parent differs.
The archive's own model bytes and the original 5090 submitted graph have not
been individually rehashed/recovered; do not infer equality from tar names.

## Frozen A100 side

- Formal input preflight: D:
  `a100-perf-pilot/h3-a100-ab-20260925-163222/evidence/preflight.json`.
  It verifies 13 SHA-256 inputs: six model/LoRA files, U02 prompt source,
  four PNG references, runner `gpu_adapt.py`, and the deployed KJNodes file;
  it separately verifies the U01 parent MD5. The current repository's U02
  prompt and four PNG files were rehashed and still match that preflight.
- Formal submitted C1 graph: D:
  `a100-perf-pilot/h3-a100-ab-20260925-163222/evidence/C1/submitted_graph.json`,
  SHA-256 `c248b91d087d089986b2e688284643bc2b6ad93e4ed1b0ee446f8438f4091225`.
  C2 and S1 are equal to C1 under the existing reviewed normalization of
  only attention routing and output prefixes (`h3_a100_ab_contract.py`).
  C1 has 35 nodes, Sage patch node 58, `SamplerCustomAdvanced` node 226,
  Euler sampler, beta 16-step schedule sliced to 12 executed steps, and
  24 fps H.264 MP4. Keep the exact graph and archived source identities as
  evidence; do not regenerate them from the now-dirty workspace.
- Formal C1/C2 A100 server/sampler wall: 1324.348/1208 s and
  1322.164/1206 s. They ran in one A100 assignment with separate ComfyUI
  process runs, not separate cloud sessions and not a 5090 multiplier.

## Read-only comparison contract for a future 5090 window

Use the archived C1 graph as a fixed comparator, not the mutable
`run_ep_units_profiled.py` path. Capture the **actually submitted** rental
graph before evaluating timing. Assert the 5090 Sage node 58 class and exact
model edge **before** applying the A/B normalizer; unexpected bypass fails.
The graph-diff allowlist is nodes 264/400 output prefixes and one declared
node 401 parent-path alias to a unique, SHA-256-verified staging file. Never
overwrite the existing production parent. For this profile, node 58 must
remain present, although its deployed SM120 binary is recorded separately.
Reject changes to prompt,
references, parent latent, model/LoRA paths and bytes, seed, scheduler,
executed steps, resolution, quantization, and all other graph inputs.
`graphs_match_except_candidate()` supplies a strict existing fixture-tested
normalizer (18 tests pass); its success is necessary but not sufficient:
record binary/source IDs, startup flags, hashes, and cache/process state
outside the graph.

The 5090 receipt must include GPU/driver/clocks, Python/Torch/CUDA/Sage
identity, six model hashes, 13-input manifest plus parent SHA-256, submitted
graph and diff, process cold/warm state, server/sampler/each-step wall,
5-second utilization/VRAM, setup/restore/backup wall, new prompt/history,
12 executed-step proof, and MP4/latent validation. Record decoded video and
PCM-audio hashes **plus** frame/audio counts, timestamps, duration and time
bases. `h3_a100_media.py::media_timeline()` now supplies the offline
ffprobe frame-level timing record; tests demonstrate that a metadata-only
remux is ignored while a timestamp shift is detected. Keep full media in
its existing store and copy only small receipts to D unless required.

Gate 0 is **not fully closed** because the offline manifest, profile-aware
comparator, prompt-bound receipt validator and runbook still need implementation
and fixture tests. A live 5090 graph or server timing is **Gate 1 evidence**,
not a prerequisite to closing the zero-CU Gate 0. Gate 1 requires both an
already-needed rental window and explicit authorization for this U02 input,
transfer, telemetry, output and bounded cost; otherwise wait. Do not restart
the rental environment just for this screen.
