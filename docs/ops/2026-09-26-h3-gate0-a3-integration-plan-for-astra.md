# H3 Gate 0 A3: integrate provenance and freeze the Stage B handoff

Status: **Astra PASS for the zero-CU A3 implementation plan only; not
Stage B execution approval**. This is a zero-CU, offline follow-up to the A2
implementation. No rental/Colab start,
model transfer, ComfyUI restart, live `/prompt` call, blind-map access or
new video sample is in scope. The frozen comparison manifest and archived
A100/5090 artifacts remain unchanged.

## Verified starting point

- A2 added a single-socket WebSocket observer, prompt/client/node-226
  snapshot parser, tiered history receipt, source-side output/latent checker
  and GPU telemetry checker. The local focused suite returned `64 passed`.
- Archived A100 C1 history plus its submitted graph and parent replayed to
  1324.348 s server wall, empty cached-node list and the frozen parent SHA.
  C1 has no captured WS trace, so its event-derived steps and sampler wall
  remain unknown. Its history output paths are reported, not byte-verified
  by that replay.
- `ComfyClient.queue_prompt()` sends `client_id`, but
  `run_ep_units_profiled.py` creates the client internally and also rewrites
  job files, uploads assets and downloads media. It must not be reused as a
  read-only Gate 0 audit or silently altered for this comparison.
- The older receipt CLI now says `STRUCTURAL_ONLY`; source deltas without a
  reviewed file-specific hash/size allowlist are `INCOMPARABLE`.

## Gap to close, without paying for another GPU session

The A2 helpers are individually tested but not a single **admission
decision**. In particular, `h3_gate0_receipt.py` currently labels a
history-only result `server_wall_screen_sampler_unknown` even if source-side
output bytes and telemetry have not been verified. That label should be
reserved for a valid already-authorized run whose history, graph, parent,
media and required environment evidence all pass, but whose WS steps were
lost. The receipt must not promote supplied paths or manually entered
measurements into `derived_verified`.

The observer and future submitter also need a narrow, reviewable handoff.
The observer writes a fresh client ID after the status handshake, while a
separate one-shot submitter must use that ID and atomically publish the
returned prompt ID. The current observer can miss a terminal event if it
arrives before that file is published; the raw trace should be reconciled
after prompt-ID publication without inventing events. An ambiguous HTTP
response must not trigger another `/prompt` call.

## A3 offline work package

1. **Make the evidence state machine explicit.** Introduce a small pure
   evaluator plus one narrow raw-artifact loader, not a second receipt
   schema. Recompute hashes and call existing validators from raw paths;
   never trust a supplied `tier=derived_verified` flag or success boolean.
   Bind everything to one run ID, prompt ID, observer client ID, frozen
   manifest and submitted-graph SHA-256, target history SHA-256, parent
   SHA-256, output byte hashes and telemetry raw hash. Include process,
   environment and deployed source identities as explicit inputs, not
   inferred from graph equality. Check history/cache/server wall, observer
   trace, source-side node-264 MP4 and node-405 latent, and telemetry raw
   hash + GPU UUID/index/time coverage. Emit per-field
   `derived_verified`/`reported_only`/`unknown` and one overall decision,
   in precedence order: `INCOMPARABLE` for any contradictory critical
   evidence; `HISTORY_ONLY_NOT_SCREEN` for absent required evidence;
   `server_wall_screen_sampler_unknown` only when all non-WS evidence passes
   after one authorized sample; `deployment_combination_screen` only when
   that evidence and the full prompt-bound 12-step WS sequence pass. Neither
   success label means hardware-only parity, sampler-wall parity or visual
   quality acceptance. Keep `observed_node_interval_s` separate from the
   A100 tqdm 1208/1206 s numbers.
2. **Freeze an at-most-once client-ID handoff contract.** Design a separate
   minimal submit boundary for a *prebuilt, hash-checked* graph. It reads
   only the observer's fresh, atomically published ready file. This record
   binds endpoint, run ID, graph hash, client ID and observer state. Before
   transport, one contender atomically claims and persists a unique attempt
   ID; duplicate or concurrent contenders cannot send. A failed, timed-out,
   ambiguous or crashed attempt remains consumed. It must not call uploads,
   rewrite a graph, start ComfyUI, use the existing profiled runner, retry a
   POST, or submit a second prompt.
   Atomically publish prompt ID without overwriting a prior file on an
   unambiguous success. On timeout or unknown response, stop and preserve
   evidence for operator inspection;
   no automatic retry/cancel. In A3, mock-test payload, competing claims,
   duplicate invocation, response loss and prompt-ID publication failure;
   **do not connect to a real ComfyUI `/prompt`**.
   A runnable live submitter remains a separate Stage B diff/admission.
3. **Close observer race and failure semantics offline.** Keep one socket
   and no reconnect. Use a bounded file check or independent await so that
   prompt-ID publication is noticed even if `ws.receive()` gets no further
   message. Reconcile prior target terminal events without rewriting raw
   events; record reconciliation separately. Require exactly one target
   terminal and monotonic receive timestamps. Distinguish pre-submit
   handshake failure (STOP) from post-submit disconnect/missed steps
   (sampler unknown).
   Synthetic fixtures cover stale ready/prompt files, late prompt ID,
   duplicate terminal, wrong client ID, malformed JSON/binary previews,
   missing WS steps and ambiguous submit response. The adapter must not
   infer success from a terminal event alone; history remains decisive.
4. **Strengthen source-side media and telemetry contract.** Pin supported
   audio properties from frozen A100 evidence, not guesswork: C1 validation
   records AAC, start 0, duration 12.736 s and `audio_max_db=-0.4`, but
   omits sample rate and channel count. Check those against approved primary
   evidence when available; until then mark them unknown rather than assert
   parity. If the approved audio contract cannot be frozen before Stage B,
   do not promote media to a matched-screen PASS. Verify AAC/video start
   and duration within reviewed tolerances, decoded non-silence and audio
   timeline; inject a whole-audio-shift
   negative fixture. Bind telemetry UUID/index to the same run's captured
   environment GPU mapping and process interval. UUID agreement alone
   cannot prove the sensor observed the actual H3 execution; sensor
   values stay `reported_only`.
5. **Rehearse all offline evidence paths.** Replay archived C1
   history/graph/parent once more through the integrated evaluator, with
   media/WS absent correctly resulting in `HISTORY_ONLY_NOT_SCREEN`.
   Validate source-side MP4/latent/telemetry components using local fixtures
   and negative mutations. No full archived MP4/latent copy to D just for
   this review. Keep reference and candidate source identities separate
   from graph equality; the current frozen manifest contains no approved
   source delta. Run syntax checks and focused regression, then perform a
   read-only diff review of the new boundary and update the runbook.

## Stage B admission only after A3 review

The next paid 5090 window requires *new explicit authorization* for the
fixed A100-parent U02, exact small transfers, read-only runtime capability
check, one observer, one prompt, outputs, bounded time/money and stop
deadline. Confirm the active process is the project ComfyUI rather than
the provider default, all required model/source hashes match or have a
reviewed allowlist, graph and parent match, unique output prefixes are empty,
and the one-shot client-ID path is reviewed. Missing large models means
STOP, not an automatic 45 GiB restore. Capture setup/restore/transfer,
server wall, output verification and backup separately. After the single
sample, no retry/U03/A100 rerun. Stop only resources **owned by this task
and explicitly authorized for shutdown**, then verify their stopped state
and billing. Never automatically stop a shared rental instance or the
team's ComfyUI merely because this sample completed; return control to its
owner and record the continuing billing boundary. A missing WS step after
submission can only downgrade the already-authorized result; it does not authorize a
second sample.

## Acceptance and review questions

A3 is done only when an independent review accepts the integrated decision
contract, offline fixtures and runbook, and no `HISTORY_ONLY_NOT_SCREEN`
result can be printed as a performance screen. This may close *offline
Gate 0 preparation*, not Stage B admission or production adoption.

1. Is a pure decision evaluator plus a mock-tested one-shot payload/handoff
   the smallest sufficient bridge, or does it overbuild Gate 0?
2. Are the four overall decisions correctly ordered, especially the
   non-WS server-wall downgrade requiring verified media and telemetry?
3. Does the proposed late-prompt-ID reconciliation preserve event identity
   without disguising a disconnect or ambiguous POST?
4. Which checks must remain Stage B runtime checks rather than being
   declared passed by offline fixtures? Identify any blocking omission or
   unsafe coupling to the production runner.

## Astra review outcome

The first review was `CONDITIONAL` on five points: same-run raw-evidence
binding, late prompt-ID handling without another WS message, at-most-once
submission claim, audio/GPU mapping boundaries and shared-resource shutdown.
After the revisions above, Astra returned **PASS** for the *zero-CU A3
implementation plan*. Acceptance must still prove missing evidence never
upgrades to a screen, concurrent/duplicate submissions hit mock transport
at most once, and an already observed terminal plus a later disconnect is
not incorrectly converted to success. This is not code acceptance, Gate 0
closure, live endpoint validation or a paid-window authorization. Both
reviews were read-only and used no GPU.
