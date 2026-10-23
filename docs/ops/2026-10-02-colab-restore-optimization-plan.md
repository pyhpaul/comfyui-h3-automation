# Colab restore optimization pilot

Status: same-VM A/B completed, both inventories verified, paid VM stopped.
Measured restore reduction: 673.517 s to 253.580 s (62.35%). Full evidence
and scope limitations are in `2026-10-02-colab-restore-optimization-results.md`.

## Scope and authorization

- Keep the serial restore as the default and comparison baseline.
- Change only split-model transport: four bounded concurrent downloads with
  ordered assembly and the existing final SHA-256 gate.
- Do not change models, Drive snapshot, source archives, GPU profile or inference.
- Operator authorized one G4 assignment, at most 5 CU and 30 minutes,
  restore only, followed by immediate stop and zero-assignment verification.
- Do not touch existing unrelated changes or historical backup artifacts.

## Evidence and experiment

The 2026-09-27 G4 raw logs show 627.11 s restore, including 606.46 s
model restore, versus 24.25 s Torch preinstall and 31.40 s software setup.
The current serial script starts a separate rclone process for each of the
76 large-model parts and blocks assembly on each individual download.
Its pre-change SHA-256 is
`ff867f0bd1608af45e883b4b1a64d9053630e1fafac3ede6b3df0abca390a849`.

Run baseline then candidate in distinct initially empty directories on the
same new G4 VM. Record restore/model times, per-model transfer/assembly
metrics, input script hashes, all six model hashes and disk free space.
No local files from the first run may be reused by the second run. Remote
Drive caching and run-order bias cannot be excluded by a single pair.
Report restore-stage acceleration, not inference or service-ready speedup.

The candidate keeps completed parts until that model passes full SHA-256,
then removes only its own cache files. Failed attempts can reuse size-checked
parts, but never publish a model without complete SHA-256 verification.
This uses extra disk space (up to one large model) rather than extra RAM.

## Tasks

- [x] Add tests for bounded concurrency, out-of-order completion, retries,
  bad size/hash, preserved existing output and retained-cache recovery.
- [x] Add opt-in fast restore without changing default serial behavior.
- [x] Add an isolated remote A/B measurement driver and bounded host runner.
- [x] Run syntax checks, targeted regression tests and host dry-run.
- [x] Verify account idle state, balance, G4 identity and disk capacity.
- [x] Execute one bounded paid A/B; stop on any failed verification/timeout.
- [x] Verify zero active paid assignments and summarize time/CU evidence.

Offline validation: 38 targeted tests passed; compileall, diff whitespace
check and watchdog shell syntax passed. Host dry-run emitted
`paid_started=false`. Pre-run account read showed 85.73 CU, zero active
assignments and 0.00 CU/hour. These do not prove a live speedup.

## First attempt and revised bootstrap

Session `h3-restore-20261002-083844` allocated G4 at 8.90 CU/hour.
The small rclone configuration upload succeeded, but the 32 MiB rclone
gzip upload did not complete within the 60-second host deadline.
The host stopped and verified the assignment; neither model restore ran.
Host wall was 72.473 s; the before/after-stop usage snapshots both showed
85.73 CU, with zero assignments after stop. Settlement can lag; rate-times-
host-wall is a conservative approximate 0.18 CU, not an invoice.

Replace this binary upload with an in-VM download from the official pinned
rclone v1.75.1 release. Accept it only if the extracted binary matches the
historical gzip's independently computed binary SHA-256:
`f66d8c1d552ad90296a11bc8b46d56a7fa5da1a7fa05e7ca522d95df92c4a4c0`.
This does not establish the root cause of the CLI upload stall.

A local official-release download also timed out after 60 seconds with
32,798 of 31,470,505 bytes. Its incomplete ZIP is retained as a failed
diagnostic artifact, not accepted as a bootstrap asset.

The revised bootstrap and host gates passed 40 targeted tests and compileall;
dry-run still emitted `paid_started=false`. Full-suite collection failed for
missing `aiohttp` in two unrelated Gate0 test files; it did not run to completion.

A notebook-stdout regression was reproduced and fixed before any retry:
the measurement Tee must forward to the active Jupyter stdout, not
`sys.__stdout__`. The remote driver also does not rely on `__file__`, which
is not guaranteed for notebook cell execution. Final targeted count: 41.

The operator authorized the second allocation by asking to continue.
Its limits are reduced to 4.8 CU and 28 minutes to keep both attempts
within the original cumulative 5 CU / 30-minute authorization.

Before allocating, a remote-file metadata read failed with OAuth
`invalid_grant`. The existing dedicated `drive.file` connection was
reauthorized through its normal browser consent flow; no scopes were added.
The immutable 439,848,960-byte source archive was readable again. No GPU was
allocated during authorization repair.

## Second attempt and Drive-only bootstrap

Session `h3-restore-20261002-085809` passed all seven small control
uploads and G4 identity (RTX PRO 6000 SM120, driver 580.82.07). The base image
now reports Torch `2.11.0+cu130`; historical runs had `+cu128`. No Torch
installation or inference was performed in this restore-only experiment.
The official rclone ZIP request from Colab returned HTTP 403. The host
required the explicit bootstrap success marker, stopped, and verified zero
assignments. Host wall was 46.001 s. No baseline or candidate restore ran.
The 403's cause was not determined; it is not evidence that Drive is blocked.

The exact retained rclone gzip was uploaded without overwriting an existing
asset to `standard-v1/runtime/bootstrap/rclone-v1.75.1-f66d8c1d.gz`.
`docs/ops/drive-rclone-bootstrap-v1.json` records its size, Drive file ID and
both archive/binary SHA-256. A direct authenticated Google Drive media download
using only the existing scoped token completed locally in 10.562 s and passed
both hash gates. This check did not allocate a GPU. The host now repeats it
before any paid allocation, also refreshing the existing token through rclone.

Validation after this change: 44 targeted tests passed, compileall and
whitespace checks passed; dry-run says eight uploads and `paid_started=false`.
The already-known full-suite missing-`aiohttp` limitation remains.

The first two attempts total 118.474 s host wall (conservatively includes
non-assignment work), approximately 0.293 CU at their observed 8.90 CU/hour.
Both after-stop snapshots still showed 85.73 CU; this is delayed settlement,
not proof the attempts were free. A third allocation has been requested,
with its own limits reduced to 4.6 CU and 27 minutes. These plus the first
two conservative estimates remain below 5 CU and 30 minutes. The operator
explicitly authorized this third attempt in the remaining cumulative budget.

Third session: `h3-restore-20261002-090853`, 8.90 CU/hour, eight small control
uploads, identity gate and minimum 110 GiB free-space gate passed. Drive-only
rclone bootstrap on Colab passed in 3.36 s. Baseline restore has started;
neither a final candidate time nor a complete model hash pair exists yet.

Final third-session outcome: serial restore 673.517 s, four-worker restore
253.580 s, additional six-model SHA readback 22.082 s / 22.066 s. Both
inventories matched. Candidate reused zero local parts. Host exited zero,
then a fresh listing confirmed no active sessions. Final usage was 0.00 CU/hour.
Three host-wall windows totaled 1,132.477 s, implying approximately 2.80 CU
at the observed rate; balance settlement was still incomplete. No further
paid test or production-entrypoint switch was performed.
