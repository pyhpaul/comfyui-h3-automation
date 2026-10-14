# Colab restore optimization: measured result

Status: one same-VM A/B completed, both model inventories verified, paid VM
stopped. This is a restore-stage result, not full service-ready timing.

## Outcome

| Phase | Serial baseline | Four-worker candidate |
| --- | ---: | ---: |
| Source, runner, six models, parent restore | 673.517 s (11m 14s) | 253.580 s (4m 14s) |
| Model subset, including assembly and restore checks | 658.980 s | 241.040 s |
| Additional independent readback of six final model files | 22.082 s | 22.066 s |

Restore saved **419.937 s (about seven minutes), 62.35%**, for a 2.656x
ratio of baseline/candidate time. Including the additional readback, the
measured restore-plus-verification times were 695.599 s and 275.647 s.
Dependency installation, ComfyUI startup and inference were not performed.
Do not call 253.580 s the full environment-to-ready time.

## Method and integrity

- One new G4 assignment: `h3-restore-20261002-090853`.
- RTX PRO 6000 Blackwell Server Edition, SM120, 97,887 MiB reported VRAM,
  driver 580.82.07; Python 3.13.15. Base Torch was `2.11.0+cu130`.
- Baseline first, candidate second, in separate initially absent directories.
  Same frozen Drive snapshot, archive hashes, model parts, parent and rclone
  binary. No local model files or cached parts were shared between runs.
- All six final models were read again and matched the size and SHA-256 in
  `docs/ops/drive-restore-rental-20260924-v1.json`, on both runs. Total model
  size was 41,651,185,023 bytes (38.79 GiB).
- Candidate large-model metrics report zero reused parts for all three models.
  Ordered assembly and full-model SHA-256 remain mandatory before publication.
- Host required the terminal success marker, session identity, exact model
  inventory and expected uploaded script hashes; it exited zero.
- Initial free disk was 207,467,433,984 bytes. After both retained model sets,
  free disk was 122,046,988,288 bytes. Candidate cache is deleted per model
  only after its final hash passes; peak extra cache can reach one large model.

This is one paired observation, not a guaranteed speedup. The same VM and
separate empty directories exclude local-file reuse but do not exclude Drive
edge caching, run-order effects or changing network conditions. The additional
readback is outside restore timing and is shown separately for both variants.

## Candidate critical-path observations

| Split model | Candidate wall | Waiting for ordered parts | Assembly/hash/write |
| --- | ---: | ---: | ---: |
| Video VAE | 18.607 s | 15.343 s | 3.051 s |
| Qwen encoder | 91.179 s | 37.601 s | 52.536 s |
| Hybrid diffusion model | 121.288 s | 20.886 s | 98.922 s |

Download-task seconds in the JSON are summed across overlapping workers;
they are not wall time and must not be added to these assembly times.
The largest model spends most of its recorded wall time in local assembly,
hashing and writing. This suggests measuring local I/O next rather than
blindly increasing concurrency to eight. Four workers already give a useful
observed reduction without removing integrity gates.

## Bootstrap failures, recovery and budget

The first two allocations did not perform model restore:

1. `h3-restore-20261002-083844`: 32 MiB binary upload exceeded 60 seconds;
   stopped and verified idle, host wall 72.473 s.
2. `h3-restore-20261002-085809`: controls and GPU identity passed, but the
   official ZIP request from Colab returned HTTP 403; stopped and verified
   idle, host wall 46.001 s. The reason for 403 was not established.

An expired dedicated Drive authorization was renewed before the second
allocation, without adding scopes. The exact saved rclone gzip was then
published under the dedicated Drive runtime/bootstrap directory, outside the
immutable model snapshot. Archive and binary hashes were verified locally;
the same authenticated Drive bootstrap succeeded on the third VM in 3.36 s.
`docs/ops/drive-rclone-bootstrap-v1.json` records the non-secret asset metadata.
No real credentials were added to project files.

Third host wall was 1,014.003 s. All three conservative host-wall windows
total **1,132.477 s (18m 52s)**. At the observed 8.90 CU/hour they imply
about **2.80 CU**, below the cumulative 5 CU / 30-minute authorization.
Host wall includes some non-assignment work; this is a rate-times-wall
estimate, not an invoice. The observed balance changed from 85.73 to 83.73
CU by the final stop snapshot; settlement may lag. Do not claim a final
2.00-CU bill or exact separate phase charges.

Final snapshots and a fresh server-side session listing confirm zero active
assignments and 0.00 CU/hour. The experiment watchdog is no longer running.

## Artifacts and replay

Evidence root: `runs/h3-restore-20261002-090853/`:

- `report.json`: timings, model readback hashes, worker metrics and code hashes.
- `colab_h3_restore_benchmark.py.log`: streamed remote execution and result.
- `inputs.json`, `cu-snapshots.jsonl`, `host-wall.json`: inputs and budget evidence.
- `stop.log`, `sessions-after-stop.log`, `colab-session.jsonl`: release and history.

Opt-in implementation: `scripts/ops/colab_h3_restore_fast.py`.
The default `colab_h3_restore.py` entrypoint still uses serial restoration;
formal generation drivers had not been switched at measurement time. Use the fast script with
its base module available on the VM, or inject its callback as the benchmark
does. Failed-run part reuse was tested offline, not fault-injected on Colab.

Subsequent integration now routes the source-controlled G4 and telemetry
entrypoints through a four-worker default with explicit serial rollback.
See `2026-10-02-colab-fast-restore-integration.md` for the offline verification
and limits. The original serial library and measured remote A/B code were
not changed by that integration; historical A100 entrypoints remain unchanged.

Dry-run, with no allocation:

```bash
.venv/bin/python scripts/ops/colab_h3_restore_benchmark_host.py --max-cu 4.6 --max-minutes 27
```

`--check-bootstrap` validates live Drive metadata, downloads and checks the
exact binary locally without allocating a VM. `--execute-paid` is a separate
explicitly billable action requiring fresh operator authorization.

Validation: 44 targeted tests passed; compileall and whitespace checks passed.
Full-suite collection remains blocked by missing `aiohttp` in two unrelated
Gate0 test files; no full-suite pass is claimed.
