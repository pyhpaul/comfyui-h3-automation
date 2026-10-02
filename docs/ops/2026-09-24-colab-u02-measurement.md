# Colab U02 measurement protocol (2026-09-24)

Status: protocol executed on the second Colab VM; measured values and verified
artifacts are in `2026-09-24-colab-u02-results.md`. The gate used the unchanged
EP04 manual-v16 U02 `motion_latent` run with the U01 AV latent as parent. No
model, workflow, startup-flag, sampler, or reference tuning was introduced.

## Evidence locations

- Local upload logs: `D:\comfyui-h3-backups\rental-20260924-5090\drive-stage\logs`.
- Local stage-2 record: `D:\comfyui-h3-backups\rental-20260924-5090\colab-stage2`.
- Colab metrics during the run: `/content/h3-u02-metrics`.
- Colab output during the run: `/content/h3-u02-results` and
  `/content/h3-rental/ComfyUI/output`.
- Dedicated Drive restore prefix:
  `comfyui-h3-colab-dedicated/rental-20260924-5090`.

Never put `rclone.conf`, an OAuth token, or client JSON in the metrics bundle.
Keep the original provider backup and the stage-1 U01 artifacts separate from
stage-2 derived results. Copy the U02 results and metrics off the VM, then
verify size and SHA-256 **before** stopping it.

## Measurement sequence

1. **Preflight without GPU.** Finish the local-to-Drive upload. Check all six
   selected model objects (three direct and 76 split parts), source archive,
   runner archive, U01 parent latent, byte counts, and remote hashes. Save the
   upload logs and actual start/end timestamps. Record a `pre_assignment` CU
   snapshot. Do not allocate the A100 until this gate passes.
2. **Assignment and base environment.** Record request/assignment time and
   Colab runtime/session ID, GPU type and physical VRAM, driver, CUDA runtime,
   CPU model and vCPU count, RAM/swap, `/content` disk space, OS/kernel,
   Python, and the baseline PyTorch version. Save `environment-base.json` and
   `python-packages-base.json`. Record `assigned` CU snapshot.
3. **Restore.** Wrap the existing restore script in the telemetry runner as
   phase `restore`. It timestamps every output line, stores exact wall time,
   samples GPU/RAM/disk every five seconds, and preserves the script's model
   part and hash-check markers. Report source/runner fetch and unpack, direct
   model fetch/check, each split model fetch/reassembly/hash, parent latent
   fetch/check, total transferred bytes, average MiB/s, retries/errors, and
   final disk usage. Differentiate Drive network transfer from local hashing
   and unpacking where separate timestamps exist; otherwise label the rate as
   **effective restore throughput**, not raw network speed. Record
   `restore_done` CU snapshot.
4. **Dependencies and ComfyUI readiness.** Wrap setup as phase `setup`.
   Preserve `uv` install command boundaries, startup PID, startup flags,
   ComfyUI `/system_stats`, ready time, registered workflow node check, and
   startup log. Save `environment-ready.json` and
   `python-packages-ready.json`; record `setup_done` CU snapshot. Missing
   optional nodes must be listed separately from nodes required by U02.
5. **One unchanged U02.** Wrap the existing U02 runner as phase `u02`.
   Preserve the exact job ID, bind/audit output, workflow/prompt ID,
   continuity mode and parent latent path, queue/execute/history status,
   sampler steps, output download, and wrapper wall time. Fetch ComfyUI
   `/history/<prompt_id>`, `/system_stats`, and server log. Report distinct
   durations for client submit/wait/download, ComfyUI execution, model load,
   text conditioning, sampling, VAE/audio decode, mux/save **only if the
   logs give defensible boundaries**. Do not infer per-node times from one
   total prompt duration. Report per-step sampling times when logged. Sample
   GPU utilization, VRAM used/peak sampled, power/temperature, RAM, and disk
   during all three phases. Record `u02_done` CU snapshot.
6. **Artifacts and shutdown.** Record MP4 and AV latent bytes/SHA-256,
   duration, resolution, frame rate, codecs, and audio presence; save workflow,
   `batch.json`, `run_meta.json`, `u02_timing.json`, logs, histories, and
   metrics. Copy to D: and/or Drive, verify remote/local hashes, note transfer
   time and bytes, and record `artifacts_safe` CU snapshot. Stop the Colab
   assignment, confirm zero active assignments/0 CU per hour, and record
   `stopped` snapshot.

Run phases with `scripts/ops/colab_h3_telemetry.py` copied to Colab:

```bash
python3 /content/colab_h3_telemetry.py --metrics-dir /content/h3-u02-metrics snapshot --label base --python /usr/bin/python3.13
python3 /content/colab_h3_telemetry.py --metrics-dir /content/h3-u02-metrics run restore -- python3 /content/colab_h3_restore.py
python3 /content/colab_h3_telemetry.py --metrics-dir /content/h3-u02-metrics run setup -- python3 /content/colab_h3_setup.py
python3 /content/colab_h3_telemetry.py --metrics-dir /content/h3-u02-metrics snapshot --label ready --python /content/h3-rental/ComfyUI/.venv/bin/python
python3 /content/colab_h3_telemetry.py --metrics-dir /content/h3-u02-metrics check-nodes
python3 /content/colab_h3_telemetry.py --metrics-dir /content/h3-u02-metrics run u02 -- python3 /content/colab_h3_run_u02.py
python3 /content/colab_h3_telemetry.py --metrics-dir /content/h3-u02-metrics capture
```

For this measured run, the local `colab exec --file
scripts/ops/colab_h3_phase_driver.py --env H3_PHASE=...` command invoked each
phase above, and `colab exec --file scripts/ops/colab_h3_backup.py` created
an uncompressed evidence tar, uploaded it to the dedicated Drive prefix and
verified the Drive MD5. The exact temporary restore/setup/U02 wrappers and
the rclone binary are preserved under D:
`colab-stage2/control-scripts/` with a checked `SHA256SUMS`. The tar and
backup receipt were then downloaded to D:, the tar SHA-256 was checked, and
`colab stop` was issued. OAuth config was not included in the evidence.

From the authenticated local CLI, use `python3 scripts/ops/colab_h3_telemetry.py
--metrics-dir /mnt/d/comfyui-h3-backups/rental-20260924-5090/colab-stage2 cu
LABEL` at each boundary above. `cu-snapshots.jsonl` stores the exact CLI
response and parsed balance/rate. Balance accounting can lag or be rounded:
report observed balance deltas and active runtime duration, **not** an
unsupported exact CU price for a single prompt. If a boundary's balance has
not updated, label the phase-specific CU as unresolved and use a later
settled total. A CU snapshot costs no GPU allocation by itself.

## Final report fields

| Group | Required values |
| --- | --- |
| Assignment | UTC/PDT start/end, session ID, GPU request/actual, idle time, stop confirmation |
| Runtime | GPU/VRAM/driver/CUDA, host RAM/CPU/disk, OS/kernel, Python/Torch/ComfyUI/custom nodes, startup flags |
| Upload WSL to Drive | per model bytes, part count, wall time, effective MiB/s, retries, 403s, remote check result; no CU |
| Restore Drive to Colab | per model bytes and part count, transfer/reassembly/hash boundaries, wall time, effective MiB/s, disk consumed |
| Setup | source unpack, dependency installs, ComfyUI boot/readiness, node-class check, total wall time |
| U02 | prompt ID, bind/audit result, queue/wait, server execution, sampling step count/times, decode/save, output download, total wall time |
| Resource use | sampled GPU utilization and VRAM peak, power/temperature, host RAM, disk before/after, samples and sampling interval |
| Quality/evidence | MP4/latent bytes and SHA-256, media properties, audio presence, history status, logs; visual review is a separate gate |
| Cost | CU snapshots at all boundaries, observed stage deltas, total GPU assignment time, known accounting uncertainty |

Calculate MiB/s as transferred bytes / 1,048,576 / measured seconds and
also give decimal MB/s only if explicitly labelled. Separate network-only,
network-plus-hash, and entire VM-start-to-safe-artifact rates. Do not compare
the U01 `18m34s` server prompt time with a whole U02 VM lifecycle. Preserve
failed attempts and retries in the record; do not average them away.

The five-second `nvidia-smi` samples show sampled utilization/VRAM, not a
hardware profiler trace or a continuous peak. `nvidia-smi` polling adds a
small measurement overhead that should be noted in any fine-grained speed
comparison. Unknown per-node duration and delayed CU billing must remain
explicitly unknown rather than estimated as fact.
