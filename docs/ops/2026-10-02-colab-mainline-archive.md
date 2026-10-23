# Colab mainline archive

Status: Colab functionality merged into main through PR #8;
isolated verification and operational-archive closeout complete.

## Task checklist

- [x] Inventory current Git state, existing PRs and Colab worktrees.
- [x] Preserve original dirty worktrees; prepare a dedicated shipping worktree.
- [x] Copy only the current Colab restore, diagnostic, Gate 0 and archive files.
- [x] Resolve the scope of the separate G4 chain and Test2 production work.
- [x] Review diffs, required dependencies, artifacts and sensitive-data exposure.
- [x] Verify the selected snapshot in isolation, without paid GPU operations.
- [x] Commit, push a feature branch, create a PR and verify GitHub checks.
- [x] Merge through the PR, synchronize main safely and reconcile old PRs.

## Current scope

- Frozen G4 U02 host, GPU identity, setup, prompt/receipt gates and session
  release/watchdog. Drive layout and immutable restore manifest.
- Four-worker split-model transport, serial rollback, pinned Drive bootstrap,
  restore-only A/B harness and measured-result archive. No Docker packaging.
- Archived A100 attention/profiling/memory experiments, SM80 patch and
  explicit-only A100 adaptation. Experimental flags remain opt-in.
- Cross-GPU Gate 0 graph/parent/media/provenance comparison, independent
  WebSocket capture, atomic handoff, single-submit adapter and telemetry.
- G4 EP04 U03-U05 continuation chain and its frozen Drive inputs, including
  the committed history from `codex/h3-g4-chain-prep`.
- Test2 EP01 preparation/recovery/finalization and EP02/EP03 production
  contracts, inputs, phase validation and finalization, including the
  committed history and selected working files from `codex/test2-ep01-g4`.
- Nine-image template bindings, prompt slot enumeration and unused-node
  pruning required by Test2; other prompt-token edits are not included.
- Historical planning, failed attempts, results and unresolved evidence
  boundaries are retained as records, not promoted to newly verified claims.

Pack extraction, unrelated prompt-token changes, scene-latent changes and
other unfinished manual-call work in the original worktree are not included.
No images, model weights, generated videos, OAuth tokens, `rclone.conf`,
runtime proxy credentials or raw session logs are added to Git.

## Reading order

1. `drive-layout-v1.md`, `drive-restore-rental-20260924-v1.json`: snapshot and
   Drive provenance; credentials remain in operator-local configuration.
2. `2026-09-27-h3-colab-g4-u02-result.md`: historical verified G4 sample.
3. `2026-10-02-colab-restore-optimization-results.md`: same-VM restore-only
   result, 11m 14s to 4m 14s, six model hashes matched; single paired sample.
4. `2026-10-02-colab-fast-restore-integration.md`: formal G4/telemetry entry,
   four-worker default and explicit `--restore-workers 1` rollback.
5. `2026-09-26-h3-gate0-runbook.md` and
   `2026-09-26-h3-gate0-implementation-result.md`: evidence admission and
   historical limits; do not equate fixture passes with paid-runtime validation.
6. `2026-09-27-h3-g4-chain-runbook.md`: frozen U03-U05 continuation inputs.
7. `2026-09-27-test2-ep01-g4-production-result.md` and
   `2026-09-28-test2-ep02-ep03-g4-production-result.md`: historical technical
   delivery, cost and acceptance boundaries. EP03 U07 failed its visual gate;
   its final episode remains a review candidate, not quality-approved.

## Runtime boundaries

The restored source, models and parent latent were measured; dependency
installation, full ComfyUI service-ready latency and inference were not
included in the fast-restore A/B. The integrated workflow was only verified
offline during this change. Failed-download cache resume was not live
fault-injected on a paid VM.

The single-U02 G4 host still requires explicit `--execute-paid` and has no
CU cap; its safety deadline is not a spending budget. Benchmark allocation
has separate CU/time caps. Any new assignment or generation requires fresh
operator authorization. This shipping/archival task authorizes neither.

The G4 continuation host now reuses the U02 host's bootstrap and restore
stage builder. This is a necessary integration repair: it imports the shared
small-upload contract, which no longer uploads `rclone.gz`, so it must run
the pinned bootstrap before restoring models. Both hosts default to four
workers and expose `--restore-workers 1`. This repair has offline routing
tests, not a new paid chain run.

The historical Test2 host keeps its separately tested apt-rclone/wheel
transport and serial model restore. It receives the required source modules
through the small-control upload contract, but is not silently switched to a
new transport strategy. EP02/EP03 archived phase utilities similarly retain
their original runtime boundary. Mainline archival does not imply every
historical experiment now uses the fast restore entrypoint.

## Dependencies and verification

`aiohttp` is declared in `dev` for loopback WebSocket tests and in optional
`ops` for the observer. It was previously missing from the test environment;
this archive must verify the suite with declared dependencies rather than
skip those tests. The reattach utility requires the interpreter bundled with
`google-colab-cli`; it must not print or archive runtime proxy tokens.

Fresh isolated verification on 2026-10-02:

- **294 passed** for all Colab restore, A100, Gate 0, G4 chain, Test2 and
  nine-image/GPU adaptation tests.
- Full candidate suite: **354 passed, 16 failed, 15 skipped**. Clean
  `origin/main` at `6862df8` reproduced **67 passed, the same 16 failed,
  15 skipped**. JUnit failure identities were compared as sets and were
  identical (`BASELINE_FAILURE_SET_MATCH 16`). These failures require old
  `/tmp` packs or local `jobs/ep_units`; no tests were removed or altered
  to conceal them. This is not a full-suite pass.
- Compileall of `scripts/ops`, `src` and `tests`, shell syntax checks of the
  startup/watchdog, whitespace checks and benchmark dry-run passed. The
  benchmark reported `paid_started=false`.
- Pattern scans found no private keys or common credential/token formats
  in the selected source, tests, patch or docs. Models, images, generated
  media, credentials and raw runtime logs remain outside Git.
- SHA-256 comparisons confirm all 77 selected files in the original main
  workspace and all 25 selected Test2 working files were unchanged by the
  copy/integration work. Only the dedicated shipping worktree was edited.

Replay the targeted admission suite after installing declared dependencies:

```bash
pytest -q tests/test_colab_h3_*.py tests/test_h3_a100_*.py \
  tests/test_h3_cross_gpu_gate0.py tests/test_h3_gate0_*.py \
  tests/test_h3_g4_*.py tests/test_h3_test2_*.py \
  tests/test_h3_nine_refs.py tests/test_gpu_adapt.py
```

No paid Colab allocation, inference, model transfer or live Drive check was
performed for this shipping task. No release tag is requested or created.

## Hosted closeout

- Consolidated PR: <https://github.com/pyhpaul/comfyui-h3-automation/pull/8>,
  merged at `2026-10-02T10:23:08Z` by squash through GitHub, not a direct
  push to main.
- Reviewed/tested head: `dc040851cd7beaa2f56e6153edbb332bcb4f055e`.
  Mainline merge: `d286198d497d9cf2e57b6e78174023c2762448ed`.
  A full-tree diff between these two revisions was empty after fetching main.
- GitHub reported `MERGEABLE` / `CLEAN` and an empty status-check list.
  `gh pr checks` confirmed no CI checks were reported. No remote CI pass
  is claimed; the isolated local verification above is the validation record.
- PRs #4 (G4 baseline) and #5 (continuation) were closed as superseded by
  the merged consolidation. They were not separately squash-merged again.
  Their original branches and dirty worktrees remain available.
- Local main was fast-forwarded in `.worktrees/colab-archive`. The original
  main workspace stays on its original feature branch with all dirty files
  preserved; the original Test2 worktree was likewise not switched or cleaned.
- Two stale Git worktree registrations for absent `/tmp` directories were
  pruned after a dry-run; no existing worktree files or branches were removed.

This closeout document is delivered through a separate documentation-only
PR; it does not modify or revalidate the historical paid-run artifacts.
