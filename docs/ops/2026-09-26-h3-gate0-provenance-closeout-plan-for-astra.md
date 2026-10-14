# H3 Gate 0: close the evidence-provenance gap before any 5090 screen

Status: **Astra PASS for the zero-CU A2 implementation plan only**. Two
conditional reviews led to a narrower prompt-bound event contract; the
final read-only review found no remaining plan blocker. This is not an
implemented observer, Gate 0 closure, live WS validation or Stage B
authorization. No rental/Colab start, model transfer, ComfyUI restart,
`/prompt` submission or blind-map access is authorized here. The existing plan remains
`2026-09-26-h3-post-sm80-gate0-closeout-plan-for-astra.md`.

## Why another offline step is needed

The frozen 13-input manifest, A100 parent, C1 graph and SM80 wheel passed
the actual D: archive audit. C1/C2/S1 graph dry-runs and 43 focused tests
passed. However `h3_cross_gpu_gate0.py` currently accepts a **supplied**
single-prompt log slice and several self-reported receipt fields. A log
containing one `got prompt`, one completion and 12 steps is not, by itself,
cryptographically or operationally bound to the target `/history/<prompt_id>`.
The receipt also checks media/telemetry field shape without recomputing them
from output bytes or a sampled trace. Calling this `RECEIPT_VALIDATED` could
overstate what was verified. See
`2026-09-26-h3-gate0-implementation-result.md`.

The next decision is whether the **existing prompt-bound events**, not an
invented log association, can make a future single-sample 5090 screen
auditable. Do not buy GPU time to discover that evidence cannot be captured.

## Evidence found in the archived ComfyUI runtime

The saved ComfyUI 0.34.0 source already has a `WebUIProgressHandler` in
`comfy_execution/progress.py`. It emits WebSocket `progress_state` with a
top-level `prompt_id` and per-node `node_id`, `value`, `max` and `state`.
`execution.py` sets the server's client ID from the queued prompt and
records prompt-bound start/cached/success in history. `server.py` exposes
`/ws?clientId=...`; its handler removes an existing socket with the same
ID before installing the new one. Therefore use a **new, task-unique ID**,
never an existing browser/production client's ID. The current repository
`ComfyClient.queue_prompt()` sends its client ID, but
`run_ep_units_profiled.py` creates that ID inside
the runner, so an external observer cannot assume it knows the session.
The sampler's `latent_preview.prepare_callback()` updates the progress
bar, which calls the progress hook. This is **source evidence of a possible
path**, not proof that all 12 WebSocket updates were emitted/received on
the archived or future target runtime. Progress throttling, disconnects
and version drift must be handled by a stop rule.

The archived C1 history exposes MP4 path under output node 264 (`gifs`) and
AV latent path through node 405 (`text` from node 400). Bind both files to
those fields rather than accepting arbitrary valid media paths.

## Stage A2: offline implementation and proof

1. **Prefer a narrow read-only event observer.** On a local synthetic
   WebSocket fixture, test an observer that connects **before submission**
   with a task-unique `client_id` shared only with the authorized submitter.
   Verify the WebSocket handshake/status echoes that ID before any later
   submission; never attach with a production UI/client ID or create a
   second socket with the same ID. Record raw event JSON, receive UTC and
   monotonic timestamps. Do not submit a prompt in Gate 0.
   The future Stage B submission path must explicitly expose or accept this
   client ID; the current runner's private generated ID is insufficient.
   A separate submit path or runner change requires its own diff review and
   cannot silently alter graph binding, uploads or production behavior.
   Parse `progress_state` as **snapshots**, selecting target `prompt_id`
   and node 226. A running start may carry `value=0,max=1`; subsequent
   updates must show unique transitions 1..12 with `max=12`, then a finished
   state. Repeated identical snapshots are allowed but count once; reject
   regressions, changed max after sampling starts, missing values or
   unexplained states. If events are throttled, missed, disconnected or
   bound to another client ID, mark `sampler_unknown`; do not infer missing
   steps from a shared tqdm log. Keep a bounded raw log slice only as
   supplemental diagnosis, not as independent identity proof. A disconnected
   observer never triggers an automatic prompt retry.
2. **Derive a tiered receipt from primary artifacts.** From target history,
   derive actual submitted graph, cache list and server wall. From raw
   prompt-bound WebSocket events, derive the observed step sequence and
   `observed_node_interval_s` from monotonic **observer receive** times,
   with UTC receipt times retained. WebSocket buffering/network delay and
   the node's running boundary mean this is not trusted sampler execution
   wall; do not populate `sampler_wall_s` from it. Keep the archived A100
   tqdm 1208/1206 s separate; do not calculate an A100/5090 sampler
   speedup ratio from those unlike clocks. The history server wall is the
   primary cross-environment metric. From the staged parent file, derive
   its SHA-256. The receipt must classify each field as `derived_verified`, `reported_only`
   or `unknown`. Rename the current `RECEIPT_VALIDATED...` CLI status to
   `STRUCTURAL_ONLY` until these derivations exist. A valid server-wall
   observation with missing sampler events may be reported only as
   `server_wall_screen_sampler_unknown`; it must not become a matched
   sampler comparison or a full performance-screen PASS.
3. **Bind and verify outputs at source.** Require the target history's node
   264 MP4 path and node 405 latent path, exact approved output prefixes,
   and proof that both files were created for this prompt rather than reused
   old files. Allocate a unique, approved output prefix and prove no matching
   target file existed before submission. Check no path escape/symlink
   redirection, file birth/mtime as auxiliary evidence, size/hash,
   H.264/AAC, 768x1376, 306 frames, 24 fps, about 12.75 s, nonempty audio,
   exact latent shape/dtype and
   finite tensors. Recompute decoded video/audio and timeline fingerprints
   from these **same files**. Do not derive `sampler_wall_s` from observer
   timestamps or a manually entered number. Bind telemetry by raw file
   hash, GPU UUID/device index and timestamp coverage; label sensor readings
   `reported_only`, since a hash does not prove sensor truth. Verify remote
   output size/hash after backup; do not copy full media to D for Gate 0.
4. **Constrain source differences.** The current validator accepts any
   changed source SHA if `source_delta_reason` is nonempty. Replace this
   with a reviewed, file-specific architecture-adaptation allowlist or
   `INCOMPARABLE`. A free-text reason alone cannot approve code that changes
   model loading, sampling or conditioning. Compare deployed source IDs
   outside the graph and disclose runtime/driver differences as deployment
   combination, not hardware-only parity.
5. **Replay and fault injection offline.** Replay archived A100 C1
   history/graph/log for server/cache/media paths; there is no archived
   WebSocket trace, so explicitly label A100 per-step UTC and event-derived
   sampler timing `unknown` rather than inventing them. Test synthetic
   prompt-bound event streams: complete 1..12, repeated snapshots, missing
   step, progress regression/max change, wrong prompt/client/node,
   disconnect, duplicate terminal, cached node, wrong graph, preexisting
   prefix, reused/foreign output path, media timestamp shift, wrong latent
   shape and GPU UUID mismatch. No fixture may call `/prompt` or
   mutate a live ComfyUI service.
6. **Review the reduced runbook.** Pin observer/submission client-ID
   handshake, timeouts and stop behavior. Admission rules are explicit:
   if prompt-bound progress capability is absent **before submission**,
   stop unless a server-wall-only screen was separately authorized. If
   events are lost **after submission**, do not retry or automatically
   cancel a normally running authorized prompt; preserve its valid history,
   graph and media as `server_wall_screen_sampler_unknown` and stop any
   follow-up task. Cancellation is governed only by the separately approved
   timeout/cost contract. Do not build a large arm/seal framework unless
   the prompt-bound event path fails offline and a new
   review finds its extra complexity justified. Any runtime capability
   check, small transfer, observer or prompt submission during Stage B
   requires the separate paid-window approval.

## Acceptance and boundaries

Gate 0 may close **offline** when the event observer/parser, tiered receipt,
source-side media binder, negative fixtures, limited A100 replay and
reviewed runbook are complete. It does **not** require a live 5090 sample
or proof that the future rental runtime will deliver all events. At Stage B
admission, verify the active runtime still supports the expected events;
otherwise stop before submission unless server-wall-only was preauthorized.
The A100 reference still has different process/cache conditions and incomplete
driver/clock evidence; a future 5090 result would be a
`deployment-combination performance screen only`, not an intrinsic GPU
benchmark or same-effect quality acceptance.

Stage B remains separate. Even during an already-needed rental window,
explicit approval must cover the fixed A100-parent U02, small transfers,
source-side observer, outputs and a bounded time/cost. A missing model,
changed graph/parent, invalid media or unexpected paid restore triggers
STOP/`INCOMPARABLE`. Missing progress **after** an authorized submission
allows only the labeled server-wall downgrade if its other evidence is
valid; no retry, no U03, no A100 rerun.

## Astra review questions

1. Does archived `progress_state` plus an explicit same-client-ID handshake
   give a defensible prompt/node-bound 12-step receipt, with missing updates
   correctly downgraded instead of reconstructed from tqdm?
2. Are the history output nodes 264/405 and source-side media/latent checks
   sufficient to prevent accepting an old or foreign file?
3. Are the three evidence states and server-wall-only downgrade honest about
   what one future 5090 sample can answer, given the older A100 event gap?
4. Is this the smallest offline implementation that can close Gate 0 without
   silently changing the production runner or requiring live paid proof?

## Astra review outcome

Astra accepted the archived `progress_state` route as the next offline
implementation target, provided client-ID isolation, snapshot transition
checks, source-side history output binding and explicit evidence tiers are
enforced. `observed_node_interval_s` remains an observer receive interval,
not sampler execution wall. A future missed WS sequence downgrades the
already-authorized result without retry or automatic cancellation. The
review changed no files and used no GPU.
