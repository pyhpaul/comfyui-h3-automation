# H3 post-SM80 Gate 0 offline implementation result

Status: **A2 offline provenance tooling implemented; Gate 0 remains open for
integration/review**. No Colab assignment, rental restart, model
transfer or H3 prompt was used in this work.

## Delivered

- `2026-09-26-h3-u02-comparison-manifest.json`: 13 sorted archived
  model/prompt/reference/source entries, A100 parent SHA-256, formal C1
  submitted-graph SHA-256, graph settings and observed runtime identity.
  Manifest SHA-256:
  `9a5f0d43b7e93a0fc5a3226c1970f79e88db03550cfc57dbbdcb502c5beb4609`.
- `scripts/ops/h3_cross_gpu_gate0.py`: read-only archive audit, profile-aware
  graph/parent comparator and receipt consistency validator. It rejects an
  unexpected 5090 bypass before graph normalization; permits only a
  hash-bound, non-overwriting node 401 parent staging alias and output
  prefixes; verifies prompt-specific history/graph/cache/timing and a
  single-prompt 12-step log slice. It does not submit `/prompt` or write
  output files.
- `scripts/ops/h3_a100_media.py`: decoded-stream hashes plus frame-level
  timeline fingerprints. The tests distinguish MP4 metadata remux from
  timestamp shifts.
- `2026-09-26-h3-gate0-runbook.md`: local-only commands, conditional
  rental admission and explicit `INCOMPARABLE` stop conditions.

## Verification performed

- Archive audit returned `REFERENCE_AUDIT_OK` for the actual preflight,
  C1 graph, A100 U01 parent and SM80 wheel on D:.
- C1 versus C2 and C1 versus S1 returned `GRAPH_AND_PARENT_ONLY` under the
  reviewed normalization. This is **not** a 5090 comparison or a new H3
  execution.
- Focused regression: `43 passed` across
  `test_h3_cross_gpu_gate0.py`, `test_h3_a100_media.py` and
  `test_h3_a100_ab_contract.py`. Negative fixtures cover bypass, parent
  bytes/staging path, sampler/seed/step/node changes, source deltas, stale
  receipt identity, cached/mixed steps, timestamp shift and stitched logs.
- The timeline helper read a real archived Colab U01 MP4 without error;
  this checks parsing only, not U02 media quality.

## Remaining boundary

The old validator's **supplied** log slice and self-reported receipt are now
classified `STRUCTURAL_ONLY`, not a validated performance screen. The
archived A100 logs do not independently timestamp each step. A future 5090
runtime still must prove prompt-bound WS support before submission; lack of
it means stop unless a server-wall-only screen was separately authorized.
No schema pass is an independent hardware or human-quality audit.

No existing 5090 result became comparable: its v16 parent is a different
SHA-256, and its 646-656 s observation remains client polling only.

## A2 offline provenance implementation (2026-09-26)

- `h3_gate0_progress.py` checks one prompt/client/node-226 snapshot chain:
  handshake, history cache/success, start 0/1, unique 1..12 transitions,
  finish and target terminal. Repeated identical progress snapshots are accepted;
  gaps, regressions, foreign IDs, malformed events and disconnects downgrade
  to `sampler_unknown`. Its interval is explicitly **observer receive** time.
- `h3_gate0_ws_observer.py` uses a fresh client UUID, a single read-only
  socket, handshake-gated ready file, fsynced JSON event log (binary previews
  represented by size/hash) and bounded stop.
  A local loopback WebSocket fixture passed. It never calls `/prompt`.
- `h3_gate0_receipt.py` derives graph/cache/server wall and parent SHA from
  primary artifacts and separates `derived_verified`, `reported_only` and
  `unknown`. Archived C1 replay yielded **1324.348 s server wall**, zero
  cached nodes, parent SHA
  `6def89c01d367a64be354a93dfb7e96806d236211eb0fdfcbf4bfe493a95946a`.
  Because C1 has no WS trace, its event-derived steps and sampler wall remain
  `unknown`; the 1208 s tqdm observation is not silently made comparable.
- `h3_gate0_outputs.py` provides pre-submit empty-prefix baselines and
  source-side history node-264/node-405 binding, path/symlink checks,
  MP4 codec/frame/timeline/decoded hashes and streaming F32 safetensors
  shape/finiteness checks. `h3_gate0_telemetry.py` binds raw sample hash,
  GPU UUID/index and prompt coverage while labeling sensor values
  `reported_only`. The actual C1 output bytes were not copied locally for
  this phase; media verification was fixture-based.
- `h3_cross_gpu_gate0.py` now rejects a changed source solely justified by
  free text; any delta needs a file-specific reviewed hash/size allowlist in
  the manifest. The frozen manifest has no such approval. Its old receipt
  CLI returns `STRUCTURAL_ONLY`.
- Latest focused verification: **64 passed** across provenance, cross-GPU,
  media and A/B contract tests; six touched Python modules compiled. No paid
  instance, model transfer or video task was started.

Before Gate 0 closure, review the source-side capture commands and the
separate submitter's client-ID handoff contract together. The current runner
generates its own client ID and has **not** been modified; an authorized
Stage B adapter requires its own diff review. A future live runtime check and
one 5090 sample still require a distinct bounded paid-window authorization.

## A3 zero-CU integration result (2026-09-26)

- `h3_gate0_evaluate.py` re-reads and hashes one run's raw manifest, graph,
  parent, history, handoff, assets, media, environment and telemetry. Its
  pure decision rule makes contradiction `INCOMPARABLE` before considering
  missing evidence. A100 is reference-only; missing required proof is
  `HISTORY_ONLY_NOT_SCREEN`. A fully evidenced 5090 bundle can be a
  server-wall-only screen if WS updates are lost, never a sampler-wall or
  hardware-only speedup claim.
- `h3_gate0_handoff.py` has an atomic, consumed-before-transport claim and
  injected **mock** transport only; it has no live HTTP client or submission
  CLI. The observer now publishes a run/endpoint/graph-bound ready record,
  detects a prompt ID published after the terminal event without fabricating
  WS messages, and records closure separately. No production runner changes.
- Source-side MP4 validation now checks audio/video start and duration
  alignment, monotonic audio timestamps, non-silence and optional approved
  sample-rate/channel matching. Telemetry can bind run ID and process PID
  to the captured GPU mapping. The frozen manifest still lacks an approved
  audio contract, so its current real-world evidence cannot be promoted to
  a matched media screen by supplying arbitrary CLI numbers.
- Archived C1 replay through the integrated evaluator returned
  `HISTORY_ONLY_NOT_SCREEN`: graph/parent/history hashes and 1324.348 s
  server wall derived; WS, handoff, source media, runtime asset and telemetry
  proof absent from this archive replay. This is the intended conservative
  result, not an A100 performance-screen PASS.
- Existing local stage-2 U02 MP4 and AV latent were separately read from D:
  MP4 H.264/AAC, 306 video frames, 12.75/12.736 s video/audio, 32 kHz
  stereo, non-silent; latent 38,580,184 bytes with both expected F32 shapes
  finite. These bytes are **not** the formal C1 MP4/latent and do not close
  its missing-source-evidence gap.

A3 remains pending independent **code** review and a reviewed audio-contract
source; the earlier Astra PASS covered the plan only. No GPU, model transfer,
live `/prompt` or paid resource was used during A3.

Focused A3 regression plus prior Gate 0/media/A-B contracts: **83 passed**.
`py_compile` passed for the touched Python modules. The new positive
5090 screen fixture uses a mock media decoder and synthetic run evidence;
it proves decision wiring, not real 5090 output quality. A local archived
stage-2 MP4/latent exercised the real media readers separately.

## A3 offline boundary review follow-up (2026-09-26)

- Tightened event provenance: a regressing observer UTC timestamp now
  downgrades WS progress, even if the monotonic counter increases.
- Tightened output binding: history may name only a file directly under the
  declared output-prefix directory; a same-prefix nested directory is
  rejected. Non-finite or non-positive AV timing metadata is rejected.
- Added negative fixtures for all three cases. The focused suite now reports
  **85 passed**. This is a self-review and offline regression, **not** the
  independent A3 code review, a live 5090 screen or Gate 0 closure.

## A3 telemetry binding follow-up (2026-09-26)

- Validate GPU JSONL from one byte snapshot and calculate its SHA-256 from
  that snapshot. The integrated gate re-hashes the file and refuses to
  promote evidence if the bytes changed during validation.
- Require both telemetry edge gaps to fit the same 7.5-second maximum as
  internal sampling gaps; malformed non-object JSONL lines are rejected.
- Added negative fixtures for sparse edge coverage, malformed lines and
  validated-byte hash mismatch. Focused regression: **88 passed**;
  `py_compile` passed for the six Gate 0 modules. No paid environment or
  live prompt was used. Independent code review and primary C1 audio
  contract remain open.

## C1 primary media recovery and audio evidence (2026-09-26)

- The formal C1 MP4 was still present in the dedicated Drive backup at
  `formal-ab-1/C1/downloads/EP04-U02-v16/EP04-U02-v16-pass1-ab-c1_00001-audio.mp4`.
  A non-overwriting copy was restored to the matching local D: archive
  `evidence/C1/downloads/EP04-U02-v16/` path. It is 9,947,111 bytes and
  SHA-256 `f7d9898aa135548bc5448524daf6fe893398c80411fe42db7bfe72153a8a4971`,
  exactly matching C1's archived `validation.json`.
- Local `ffprobe` 8.0.1-3ubuntu2 on those primary bytes reports one H.264
  video and one AAC audio stream, audio sample rate 32,000 Hz, 2 channels,
  stereo layout, and audio start/duration 0/12.736 s. The project
  `inspect_video(..., AudioContract(32000, 2))` returned successfully:
  306 decoded video frames, 398 decoded audio frames, video duration 12.75 s,
  audio maximum -0.4 dB. Stream `nb_frames=399` in the old validation probe
  is metadata, not the decoded-frame count; neither is substituted for the
  other.
- The matching formal C1 AV latent was also recovered without overwrite:
  38,580,184 bytes, SHA-256
  `f26dd8903b16a769ab5ccb7d36f88bdcbec571ed28148c33868512d014bab29b`,
  matching C1 `validation.json`. The current `inspect_latent()` verified
  finite F32 audio `[1,32,2,547]` and video `[1,24,97,86,48]` tensors.
- This closes the *missing primary sample-rate/channel evidence* gap, not
  the approval gate. The original frozen manifest has no audio contract and
  its SHA-256 must not be silently changed. A separately reviewed manifest
  revision or reviewed hash-bound addendum and independent A3 code review
  are still required before any 5090 screen can be admitted. No Colab/GPU
  instance, model transfer or prompt was used for this recovery.

## Independent A3 code review and technical audio addendum (2026-09-26)

- Astra's first independent **code** review found four blockers: unverified
  5090/Sage/process identity, at-most-once claim scope, incomplete handoff
  schema, and observer connection/event bounds. The subsequent read-only
  code re-review returned **PASS for those offline fixes**, not Stage B.
- The evaluator now needs reported 5090/CC12.0 identity, an actually hashed
  Sage binary, single-prompt queue state, and a canonical run namespace.
  The claim/prompt paths are derived from that namespace, graph bytes are
  read once for hash and payload, handoff endpoint/UUID/freshness are bound,
  and the observer has a total connection deadline plus event/byte caps.
  Audio frame timestamps additionally reject internal gaps; late prompt-ID
  reconciliation can retain unrelated trailing status messages without
  erasing the target terminal.
- The exact C1 primary-evidence report SHA is
  `c1235fa6115b0076dc9d2fd9bcc814ef90b27af8773721cb940f9be2a3e83f12`.
  Astra independently checked all 14 reported media fields against the
  local C1 bytes and approved the **technical-format-only** addendum SHA
  `949677963c5453c4924b9fbaef2cd49fa7063af631d2afe614c3e42ed6f89f52`.
  The base manifest SHA remains unchanged. A `review_id` alone is not a
  substitute for this pinned hash.
- `h3_gate0_evaluate.py` now accepts `--audio-addendum` and permits media
  admission only for the pinned addendum. Missing addendum stays non-screen;
  a hash or binding mismatch is `INCOMPARABLE`. Astra's final read-only
  integration review returned **PASS** for this exact pinned contract and
  canonical namespace change, not for Stage B. Its suggested missing-file,
  cross-manifest and actual-repository-addendum tests were added. Focused
  regression now reports **110 passed**; six Gate 0 modules compile. Local
  formal C1 MP4 and AV latent both pass current full media readers. The
  archive replay still reports `HISTORY_ONLY_NOT_SCREEN` because it does not
  include source-side 5090 run/handoff/telemetry/WS evidence.

None of the above starts or approves a paid 5090 window, proves same-effect
visual quality, or guarantees runtime Sage process mapping beyond the
reported and source-hashed environment capture.

## Stage B adapter offline candidate (2026-09-26)

- `h3_gate0_submit_once.py` is a separate, dry-run-by-default candidate for
  one local ComfyUI `/prompt` call. It recomputes the frozen manifest,
  reference graph, candidate graph and staged parent contract before any
  claim. Execution requires `--execute-once` and an explicit deadline;
  the transport sends one POST with the observer client ID, disallows
  redirects and retries, bounds response bytes and leaves ambiguous
  outcomes consumed for manual reconciliation.
- The existing handoff core now exposes `submit_once()` for the injected
  transport; the A3 `mock_submit_once()` test name remains as a compatibility
  wrapper. No production runner or rental ComfyUI was changed.
- Local loopback HTTP tests cover success, timeout after receipt, redirect,
  malformed and unbounded responses, slow-drip hard deadlines, graph
  mutation, duplicate/concurrent calls and no-network dry-run. The hard
  deadline now shuts down the socket without closing `HTTPConnection` from
  the timer thread, and explicit `auto_open=False` prevents a post-deadline
  reconnect. Focused Gate 0/A-B regression: **126 passed**. Astra's second
  review returned **PASS for the offline adapter race fix**; the first review
  also required the now-documented parent path/loader TOCTOU limit. This
  remains pending Stage B runtime/source/fee admission and explicit approval,
  not a live submission or Gate 0 closure.

## Stage B pre-admission continuation (2026-09-26)

- The full CLI path now has a zero-network integration fixture: default
  dry-run performs frozen graph/parent validation without a POST; an explicit
  deadline plus a mock transport consumes one ready-bound attempt and
  publishes one prompt ID. This is not a live ComfyUI framing test.
- Replayed the D: frozen-reference audit against the archived A100 C1 graph,
  preflight, U01 parent and Sage wheel: `REFERENCE_AUDIT_OK`. Replayed the
  archived C2 comparison: `GRAPH_AND_PARENT_ONLY`. The manifest SHA-256 is
  `9a5f0d43b7e93a0fc5a3226c1970f79e88db03550cfc57dbbdcb502c5beb4609`.
- Remaining `WAIT_FOR_WINDOW` gates are the actual 5090 process, source and
  six-model hashes, input/reference staging, response framing, queue/cache
  state, output baselines, telemetry, and a separately bounded rental cost
  and stop deadline. No 5090/Colab instance, asset transfer or real `/prompt`
  was used in this continuation.
