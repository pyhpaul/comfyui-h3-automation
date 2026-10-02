# G4 fast restore entrypoint integration

Status: integrated into the source-controlled G4 and telemetry entrypoints;
offline verification passed. No paid run was performed for this integration.

## Scope

- Integrate the measured four-worker transport into the source-controlled G4
  U02 host and telemetry restore entrypoints. Do not add Docker packaging.
- Retain an explicit serial option, not an automatic failure retry. Integrity
  failures still stop the host without submitting a generation prompt.
- Replace the G4 binary upload with the pinned, dual-hash-verified Drive
  bootstrap used by the successful restore-only A/B.
- Leave historical A100 drivers and immutable backup scripts unchanged.
- No paid allocation, inference, OAuth change or live-network test in this step.

## Tasks

- [x] Add failing tests for the entrypoint default, serial selection, invalid
  configuration, upload contract, bootstrap gate and stage admission.
- [x] Add a thin remote entrypoint; keep the serial library and A/B unchanged.
- [x] Share the existing host bootstrap preflight with the G4 host; upload
  only small controls and verify bootstrap before restoring models.
- [x] Add the G4 host serial override and record the chosen mode in evidence.
- [x] Update telemetry routing and document manual rollback.
- [x] Run targeted regressions, syntax checks and whitespace checks; record
  that full G4 service-ready behavior has not been retested on a paid VM.

The earlier A/B measured restore only: 673.517 s serial versus 253.580 s
four-worker. It is not a timing promise for the integrated full workflow.

## Entry and rollback

`scripts/ops/colab_h3_g4_u02_host.py` now defaults to four workers. It
uploads the base, fast and entry modules plus pinned bootstrap metadata, not
the 32 MiB binary. Its local preflight validates the live Drive asset and
downloads/verifies the exact bootstrap before allocation, refreshing the
existing token through rclone. On the VM, identity and bootstrap must pass
before Torch preinstall or model restoration.

`trial-inputs.json` records `restore_workers`, restore/bootstrap script
hashes and the metadata hash. Existing stage success markers, frozen-input
preflight, prompt receipt checks and final session release remain in place.
Neither an integrity failure nor a timeout triggers an automatic serial retry.

Default preflight, without allocating a GPU:

```bash
.venv/bin/python scripts/ops/colab_h3_g4_u02_host.py
```

Explicit original serial transport, also preflight-only:

```bash
.venv/bin/python scripts/ops/colab_h3_g4_u02_host.py --restore-workers 1
```

These preflights contact Drive and fetch the bootstrap, but do not allocate
a VM. A real U02 run still requires separately authorized `--execute-paid`;
the existing G4 generation host has no CU cap and a four-hour default safety
deadline. The completed restore pilot's 5 CU / 30-minute authorization does
not authorize a generation run or another allocation.

The telemetry phase driver routes restoration to
`/content/colab_h3_restore_entry.py`. Upload this module alongside
`colab_h3_restore.py` and `colab_h3_restore_fast.py` before using it; the
pinned bootstrap must already have produced `/content/rclone.gz`.
`H3_RESTORE_WORKERS=1` selects serial transport through this entry as well.
Only values 1 and 4 are accepted. Executing the original base script directly
still uses serial transport, preserving the historical baseline.

The fast path retains size-checked parts after an interrupted download, then
requires full model SHA-256 before publication. This uses extra disk space
up to the largest model (about 19.53 GiB); it does not pack model weights
into an image or remove integrity gates. A valid final model is rehashed
before it is skipped. Cache-resume and failure behavior were verified offline,
not fault-injected on a paid runtime.

## Verification

- Tests were first observed failing for absent entry routing, the legacy
  binary-upload contract and missing host worker selection.
- 71 targeted tests passed: restore manifest, parallel transport, entry
  routing, serial rollback, real small-model assembly through both callbacks,
  bootstrap hashes/metadata, cold A/B gates, G4 admission and A100 regressions.
- Simulated host runs prove bootstrap/restore failure stops without entering
  setup, preflight or generation and invokes the existing release path. All
  external dispatch was stubbed; no paid session was created by these tests.
- Compileall, `git diff --check`, G4 `--help` and the actual restore-benchmark
  dry-run passed. The latter reported `paid_started=false` and eight uploads.
- Full-suite collection failed for missing `aiohttp` in
  `tests/test_h3_gate0_handoff.py` and `tests/test_h3_gate0_provenance.py`.
  Dependencies and those tests were not changed; no full-suite pass is claimed.

The integrated full G4 workflow has not been live-tested. Next separately
authorized real run should verify the recorded worker mode, all stage gates,
full service-ready timing and final release. No Docker work is planned.
