# A100 combined profiler and smart-memory A/B result

Status: **paid run stopped; no active Colab assignment**. This was one A100
high-memory session, not multiple restores. The `--disable-smart-memory`
removal candidate did not improve the unchanged U02 workflow, so S2/M2 were
correctly not run. Do not promote this memory setting or restart a paid session
to repeat it.

## Frozen run and accounting

- Session: `h3-a100-combined-20260926-085346`, UTC 2026-09-26.
- GPU: `NVIDIA A100-SXM4-80GB`, SM80, 81920 MiB advertised; driver
  `580.82.07`. Colab base image initially had Torch `2.11.0+cu128`; the
  restored ComfyUI venv used pinned Torch `2.14.0+cu130` and the frozen
  SageAttention SM80 wheel.
- Same parent U01 latent, six model files and 13-input SHA preflight. The
  source, wheel, prompt and references matched the archived manifest.
- Observed rate: 6.77 CU/hour. Balance went from 158.27 to 148.18 CU:
  **10.09 CU observed consumption**, below the authorized 20 CU cap.
  `colab usage` showed `0.00/hr` and zero active assignments after exit;
  `colab sessions` showed no active sessions.
- Models restored in 816.63 seconds, including 799.15 seconds for model
  reconstruction/transfer. Source, dependencies, setup and preflight followed
  in the same runtime. The first paid phase began at 09:13:11 UTC.

## Measured phases

| Phase | Change | Result | Key measure |
| --- | --- | --- | --- |
| P_B | bypass attention, smart memory disabled | success | profiled one-step wall 125.589 s |
| P_C | Sage SM80, smart memory disabled | success | profiled one-step wall 105.602 s |
| M0 | Sage SM80, smart memory enabled | success | profiled one-step wall 104.722 s; Torch reserved peak 1.375 GiB in the instrumented step |
| S1 | full U02 Sage control, smart memory disabled | success | server 1323.563 s; sampler 1206 s; phase wall 1354.27 s |
| M1 | full U02 Sage candidate, smart memory enabled | generated valid media, but **gate failed** | server 1321.416 s; sampler 1206 s; phase wall 1345.31 s |
| S2/M2 | conditional repeat pair | not run | first-pair >=15% speed gate failed |

The one-step profiler is diagnostic, not an unprofiled throughput measure.
P_C improved on P_B by 15.9% in profiled one-step wall time, consistent with
the earlier formal Sage A/B direction. M0 improved on P_C by only 0.8% in that
instrumented step. The causal full U02 comparison improved server time by
0.16% and sampler time by 0%; it does **not** support smart-memory removal as
a speed optimization. Five-second `nvidia-smi` samples saw 35,910 MiB peak
for S1 versus 51,396 MiB for M1, a 15,486 MiB increase, without a useful
timing gain. M0's Torch allocator peak is only a one-step, instrumented
measurement and is not a full-run VRAM bound.

Both runs returned a 768x1376, 306-frame, 12.75-second H.264/AAC MP4 and
a finite AV latent of the same shapes. The two latent files have the same
SHA-256 (`f26dd8903b16a769ab5ccb7d36f88bdcbec571ed28148c33868512d014bab29b`).
Raw MP4 SHA-256 differs, but the files have the same length (9,947,111 bytes)
and differ at only two bytes: the embedded `s1`/`m1` output labels in metadata.
Independently decoded video and audio each hash identically across S1/M1:
video `28ceae0d102091d951ebfd82dc361bd4481bbc03095350449d73569044d33c04`,
audio `885a4006fd6ab1901db0c623bd3c0ec56bdc2a3a6a5950bd564bc22ec3a5d5a6`.
Thus the raw-container-hash gate was too strict for labeled files; it is not
evidence of changed picture or sound. The timing gate independently failed.
This does not replace the deferred human quality review of Sage versus bypass.

## Failure and evidence boundary

M1 finished generation and Drive backup at 10:09:46 UTC, but its phase marked
`failed` because the predeclared timing/raw-MP4-hash gate failed. The host
`colab exec` did not return that phase result; it later reported
`RuntimeError: Connection was lost.` The remote receipt was reconciled as
`failed`, not retried. By the 10:30:54 UTC host stop check, Colab already
reported zero active assignments and `0.00/hr`. The attempted `colab stop`
returned `Not Found` because the assignment was already gone; this is not
evidence of a still-billing instance. The roughly 21-minute interval after
M1's archived completion and before the failed transport returned consumed
additional billed time. A future host should poll timestamped Drive receipts
while `colab exec` is silent and stop promptly on a terminal failure receipt;
the present script only reconciles after the CLI returns or disconnects.

Evidence on D: `D:\comfyui-h3-backups\rental-20260924-5090\a100-perf-pilot\h3-a100-combined-20260926-085346\`.
Full S1/M1 MP4 and latent outputs remain on Drive under
`h3drive_h3:comfyui-h3-colab-dedicated/rental-20260924-5090/a100-perf-pilot/profile-h3-a100-combined-20260926-085346/`.
The D evidence copy excludes MP4 and safetensors but includes phase receipts,
submitted graphs, validation, step timings, 5-second GPU telemetry, logs,
profiler reports, CU snapshots and the exported Colab session history.

## Decision

Keep the proven Sage SM80 profile with `--disable-smart-memory` for the A100
U02 workflow. The remaining cost is dominated by the 12-step sampler
(1206/1323.6 seconds, about 91%). Future optimization should target the
unchanged-shape sampler/attention/quantization path, not assume that more VRAM
or less offload alone will make this workload faster. Before another paid
batch, replace raw MP4 equality with decoded essence equality or normalized
metadata and add terminal-receipt polling to prevent an avoidable silent CLI
wait. Any further model, step-count, resolution or quality change needs a
separate quality gate and CU authorization.
