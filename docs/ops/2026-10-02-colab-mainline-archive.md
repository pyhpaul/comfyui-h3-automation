# Colab mainline archive

Status: scope review and isolated verification in progress; not yet merged.

## Task checklist

- [x] Inventory current Git state, existing PRs and Colab worktrees.
- [x] Preserve original dirty worktrees; prepare a dedicated shipping worktree.
- [x] Copy only the current Colab restore, diagnostic, Gate 0 and archive files.
- [ ] Resolve the scope of the separate G4 chain and Test2 production work.
- [ ] Review diffs, required dependencies, artifacts and sensitive-data exposure.
- [ ] Verify the selected snapshot in isolation, without paid GPU operations.
- [ ] Commit, push a feature branch, create a PR and verify GitHub checks.
- [ ] Merge through the PR, synchronize main safely and reconcile old PRs.

## Current scope

- Frozen G4 U02 host, GPU identity, setup, prompt/receipt gates and session
  release/watchdog. Drive layout and immutable restore manifest.
- Four-worker split-model transport, serial rollback, pinned Drive bootstrap,
  restore-only A/B harness and measured-result archive. No Docker packaging.
- Archived A100 attention/profiling/memory experiments, SM80 patch and
  explicit-only A100 adaptation. Experimental flags remain opt-in.
- Cross-GPU Gate 0 graph/parent/media/provenance comparison, independent
  WebSocket capture, atomic handoff, single-submit adapter and telemetry.
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

## Dependencies and verification

`aiohttp` is declared in `dev` for loopback WebSocket tests and in optional
`ops` for the observer. It was previously missing from the test environment;
this archive must verify the suite with declared dependencies rather than
skip those tests. The reattach utility requires the interpreter bundled with
`google-colab-cli`; it must not print or archive runtime proxy tokens.

Verification results and merge evidence will be recorded before closeout.
