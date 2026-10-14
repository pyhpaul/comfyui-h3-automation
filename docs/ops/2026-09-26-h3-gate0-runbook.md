# H3 cross-GPU Gate 0: offline audit and conditional 5090 runbook

Status: **A3 tooling and Stage B adapter passed offline code review; runtime
Stage B remains unauthorized**.
An independent code review of the A3 blockers, the exact C1 technical
audio addendum and its evaluator integration returned PASS within their
respective offline scopes. This runbook is
not an authorization to start a GPU, transfer assets or submit a prompt.
Use `2026-09-26-h3-u02-comparison-manifest.json` as the immutable comparator;
its SHA-256 is
`9a5f0d43b7e93a0fc5a3226c1970f79e88db03550cfc57dbbdcb502c5beb4609`.
The original manifest remains unchanged. The separately reviewed C1 audio
addendum has SHA-256
`949677963c5453c4924b9fbaef2cd49fa7063af631d2afe614c3e42ed6f89f52`.
The manifest was derived from the archived A100 preflight and submitted C1
graph, not the current working tree. Keep the existing rental-5090 production
profile and the A100 formal artifacts unchanged.

## Safe to execute now: local D: archive only

From the repository root, set the evidence base for readability:

```bash
BASE=/mnt/d/comfyui-h3-backups/rental-20260924-5090/a100-perf-pilot
AB="$BASE/h3-a100-ab-20260925-163222/evidence"
MANIFEST=docs/ops/2026-09-26-h3-u02-comparison-manifest.json
PARENT=/mnt/d/comfyui-h3-backups/rental-20260924-5090/colab-stage1/ep04_u01_00001.safetensors
sha256sum "$MANIFEST"
python3 scripts/ops/h3_cross_gpu_gate0.py \
  --manifest "$MANIFEST" \
  --reference-graph "$AB/C1/submitted_graph.json" \
  --reference-preflight "$AB/preflight.json" \
  --parent-file "$PARENT" \
  --sage-wheel "$BASE/sageattention-2.2.0-cp313-cp313-linux_x86_64.whl"
python3 scripts/ops/h3_cross_gpu_gate0.py \
  --manifest "$MANIFEST" \
  --reference-graph "$AB/C1/submitted_graph.json" \
  --candidate-graph "$AB/C2/submitted_graph.json" \
  --profile a100_sage_sm80 --parent-file "$PARENT"
pytest -q tests/test_h3_cross_gpu_gate0.py tests/test_h3_a100_media.py tests/test_h3_a100_ab_contract.py
```

Expected statuses: `REFERENCE_AUDIT_OK` and `GRAPH_AND_PARENT_ONLY`. The
second status explicitly **does not** validate a new 5090 receipt. The
manifest hash, exact graph hash and parent SHA-256 are checked by the tool.
It neither writes files nor calls ComfyUI or Colab. A source/graph mismatch
returns exit code 2 and `INCOMPARABLE`.

## A100 evidence limits to disclose before a 5090 run

- C1/C2 used one A100 assignment and separate ComfyUI processes. Their
  server/sampler walls are 1324.348/1208 s and 1322.164/1206 s. Each was
  prewarmed in the same VM; neither is a fresh-machine cold start.
- The C1 server log identifies Python 3.13.15, Torch 2.14.0+cu130,
  ComfyUI 0.34.0, A100-SXM4-80GB and disabled smart memory, but the exact
  startup command and GPU driver/clocks are not fully frozen in the C1
  preflight. Do not invent those fields or claim hardware-only isolation.
- C1 history has prompt-bound start/success and an empty cached-node list.
  Its ComfyUI log has one prompt and 12 step progress entries, but does not
  carry independently timestamped per-step events. The new receipt validator
  must not backfill fake per-step UTC times into the old A100 receipt.
- The old 5090 v16 parent SHA-256 is
  `9131bac0d54ed957890fe7e24411bfc329bb6e86ac4add6608fc3915ce249376`,
  unlike the A100 parent
  `6def89c01d367a64be354a93dfb7e96806d236211eb0fdfcbf4bfe493a95946a`.
  Historical 646-656 s client polling is not a same-input denominator.

## Conditional Stage B admission; no action without explicit approval

An existing rental window is necessary but **not** sufficient. Obtain a
separate approval naming EP04-U02-v16 with the frozen A100 parent, the
34,602,712-byte parent transfer, input/reference staging, telemetry, output
writes, maximum rental time and money, and a stop deadline. Confirm that
the original team ComfyUI is the process being used; the provider's default
`/root/ComfyUI` is not the project installation at
`/root/autodl-tmp/ComfyUI`. Follow the canonical startup procedure only
inside that approved window; do not restart production merely to clear a
cache. If the window is not already needed, stop at `WAIT_FOR_WINDOW`.

Read-only preflight on the approved runtime must establish GPU/driver/clocks,
disk lifecycle and free space, ComfyUI/Python/Torch/CUDA/Sage identities,
startup flags, and hashes of all six models plus the prompt/four references.
The run environment capture must report the actual GeForce RTX 5090 name,
compute capability 12.0, GPU UUID/index, active process PID, loaded Sage
binary path and source-side SHA-256, plus a single-prompt queue state with
node 226 not cached. The evaluator re-hashes that Sage binary and does not
promote a caller-supplied `--profile rtx5090` by itself. NVIDIA lists the
RTX 5090 under compute capability 12.0 at
<https://developer.nvidia.com/cuda/gpus>.
Capture both source hashes even if the architecture-specific adapter differs.
A source delta needs an immutable, file-specific `approved_source_deltas`
entry (`sha256`, `bytes`, `review_id`) in the reviewed manifest; a free-text
reason alone is `INCOMPARABLE`. If a large model is absent or its hash differs,
**stop**: no automatic 45 GiB restore. Count all validation and transfer
time in the session economics.

Stage the A100 parent in a new, non-overwriting path such as
`output/h3_gate1/<unique-run-id>/parent-6def89c01d367a64.safetensors`.
Verify size 34,602,712 bytes and its full SHA-256 before use. Never write to
the production `output/h3_context/ep04_u01_00001.safetensors`; that path
has held different bytes. The candidate graph may differ from C1 only at
node 401 `latent_path` for this declared, hash-verified alias and at nodes
264/400 output prefixes. A production input-name collision was observed:
`id0-char-001.png` and `id2-scene-013.png` under the live ComfyUI input root
have different SHA-256 from the frozen C1 images. Do not overwrite them.
The four frozen reference images may instead be staged in the same run's
`input/h3_gate1/<unique-run-id>/refs/` directory. Only the `image` values of
the frozen LoadImage nodes 43/49/50/51 may change to those exact same-run
relative aliases, and every staged file must match its frozen size/SHA-256.
The comparator rejects reference paths with symlinked components. Confirm
the live process has no alternate `--input-directory` and uses this ComfyUI
root's `input` before trusting the path check. Node 58 **must** still be the
Sage patch with the exact edge to node 128; a bypass or any other graph diff is
`INCOMPARABLE`. In the approved window, stage **small** copies of this
manifest, C1 graph, `h3_cross_gpu_gate0.py` and its
`h3_a100_ab_contract.py` dependency on the rental node; verify
their hashes and account for the transfer. The D: paths and shell variables
above are local-only and are not available on the rental node. From the
staged repository/scripts there, run the read-only comparator against the
actual parent file and prepared graph **before submission**:

```bash
MANIFEST=/path/to/staged/2026-09-26-h3-u02-comparison-manifest.json
REFERENCE_GRAPH=/path/to/staged/C1-submitted_graph.json
RUN_ID=replace-with-approved-unique-id
PARENT_FILE="/root/autodl-tmp/ComfyUI/output/h3_gate1/$RUN_ID/parent-6def89c01d367a64.safetensors"
python3 scripts/ops/h3_cross_gpu_gate0.py \
  --manifest "$MANIFEST" --reference-graph "$REFERENCE_GRAPH" \
  --candidate-graph /path/to/submitted_graph.json \
  --profile rtx5090 --run-id "$RUN_ID" \
  --output-root /root/autodl-tmp/ComfyUI/output \
  --input-root /root/autodl-tmp/ComfyUI/input \
  --parent-file "$PARENT_FILE"
```

That command is a **pre-submit graph, parent and reference-byte check**, not
a prompt submission. Its legacy status name is `GRAPH_AND_PARENT_ONLY`.
Do not use the
mutable `run_ep_units_profiled.py` path as a read-only audit. The exact
submission mechanism and target process must be reviewed at the paid-window
admission, with a new prompt ID and one output prefix that cannot collide
with production outputs. An offline Stage B candidate adapter is now
`h3_gate0_submit_once.py`; its default mode is **dry-run with no POST**. It
rechecks the frozen graph/parent, and a live call additionally requires
`--execute-once --deadline-utc` with a deadline no more than two hours away.
It only allows local plain HTTP, makes one bounded `/prompt` POST with the
observer client ID, never redirects/retries/uploads/polls, and leaves an
ambiguous attempt consumed for operator reconciliation. This adapter is
**not** a source/model audit or paid-window approval. At admission, stage
it with `h3_gate0_handoff.py`, `h3_cross_gpu_gate0.py` and
`h3_a100_ab_contract.py`, then verify the staged adapter matches the reviewed
source bytes and independently inspect the exact target process and all
runtime assets before enabling
`--execute-once`. Do not run U03 or automatically retry an uncertain U02.

The graph bytes are rehashed by the handoff immediately before its durable
attempt claim; this detects a graph changed after the CLI preflight. The
parent and four reference images are different: the CLI hashes their staged
bytes during preflight, but ComfyUI later opens them by path. Keep those new
staging paths immutable from preflight through node load, rehash every file
immediately before submission and again after the run, and mark any mismatch
`INCOMPARABLE`. Even matching before/after hashes do not prove the exact
bytes read by ComfyUI; that would require loader-side hashes captured for
this prompt. The local at-most-once
claim applies only to invocations sharing the same persistent `run_dir`;
it is not a global server-side deduplication guarantee. A response without
bounded `Content-Length`, including chunked framing, is an ambiguous
consumed attempt, not proof that ComfyUI did not queue the prompt.

## A2 provenance contract for a separately approved Stage B window

The old `--receipt --history --sampler-log` path is now explicitly
`STRUCTURAL_ONLY`. An isolated tqdm log is supplemental diagnosis, **not**
prompt-bound proof or a trusted `sampler_wall_s` source. For an authorized
single sample, use these source-side boundaries in order:

1. Freeze a new output root/run ID and two unique node-264/node-400 prefixes.
   Run `h3_gate0_outputs.py baseline --output-root ROOT --prefix PREFIX
   --run-id RUN_ID`
   once for each prefix **before** submission, save the JSON and require
   `files: []`. No existing files may be overwritten.
2. Read the active runtime's `progress.py`, `server.py` and submission route
   before submitting to confirm the archived prompt-bound `progress_state`
   contract is still present. This is a capability check, not proof that
   updates will be delivered. Start exactly one
   `h3_gate0_ws_observer.py --url ws://HOST/ws --ready-file READY
   --trace-file TRACE --prompt-id-file PROMPT_ID --run-id RUN_ID
   --graph-sha256 GRAPH_SHA --timeout-s LIMIT` before
   submission. It creates a fresh UUID4 client ID and writes `READY` only
   after `status.data.sid` echoes it. The ready record is atomically
   published with run ID, endpoint and graph hash; JSON events are fsynced
   to `TRACE.events.jsonl`. The separately reviewed submitter must use
   **that same client ID**; the current runner generates its own and is not
   an acceptable silent substitute. Never open another socket with that ID:
   ComfyUI replaces its previous socket. A separate at-most-once claim must
   precede any POST. Keep `ready.json`, `attempt.json` and `prompt.json`
   in one persistent `<state-root>/<run-id>/` directory; copying `ready.json`
   to a new directory is **not** a recovery method. An unambiguous response
   publishes the prompt ID JSON atomically. A failed or ambiguous claim is consumed,
   with no retry. The observer stops on that prompt's terminal
   event or bounded timeout/disconnect; connection setup is part of the
   deadline and event capture is bounded by 4096 events / 16 MiB of frame
   payload. It never submits/retries/cancels.
3. Preserve `/history/<prompt_id>` and the actually submitted graph.
   `h3_gate0_receipt.py --history HISTORY --submitted-graph GRAPH --prompt-id
   ID --parent-file PARENT --trace TRACE` derives history graph/cache/server
   wall, parent SHA, ordered WS steps and the **observer receive** interval,
   but remains `HISTORY_ONLY_NOT_SCREEN` without source media and telemetry.
   It leaves `sampler_wall_s` unknown. The archived A100 C1 has no WS trace;
   no A100/5090 sampler-speed ratio may use unlike clocks.
4. On the source machine, run `h3_gate0_outputs.py verify --output-root ROOT
   --history HISTORY --prompt-id ID --video-prefix VIDEO_PREFIX
   --latent-prefix LATENT_PREFIX --video-baseline VIDEO_BASELINE
   --latent-baseline LATENT_BASELINE --run-id RUN_ID`. It binds node 264 MP4 and node 405
   text (edge from node 400), rejects prefix reuse/path escape/symlinks,
   checks modification time as auxiliary evidence, H.264/AAC 768x1376,
   306 frames at 24 fps, ~12.75 s, nonempty audio and finite F32 latent
   tensors of the exact two expected shapes. It additionally checks audio
   start/duration alignment, non-silence, sample rate and channel count
   when an approved contract is supplied. It recomputes byte, decoded
   stream and timeline hashes from those same files. Record backup-side
   size/SHA after transfer; no full media transfer to D is needed for Gate 0.
5. Preserve raw GPU JSONL, GPU UUID/device index and its SHA-256. The
   `h3_gate0_telemetry.py::verify_telemetry()` helper checks identity and
   sample coverage (including both edge gaps, each at most 7.5 s) against
   the run ID/process PID/environment GPU mapping; the integrated gate
   re-hashes the exact validated JSONL bytes before admission;
   utilization and VRAM sensor values remain
   `reported_only`. Record setup/restore/transfer/backup times separately.

`h3_gate0_evaluate.py` is the read-only overall decision gate. It rereads
and hashes raw manifest, graph, parent, history, handoff, assets, output,
telemetry and environment files from **one run**. Contradiction wins
(`INCOMPARABLE`); missing required evidence is
`HISTORY_ONLY_NOT_SCREEN`. Only a complete source-side 5090 bundle can
become `server_wall_screen_sampler_unknown` or, with 12 prompt-bound WS
steps, `deployment_combination_screen`. Supply the exact approved C1 audio
addendum using `--audio-addendum`; a missing addendum is non-screen, and a
different SHA-256 is `INCOMPARABLE`. The addendum pins C1 primary MP4 bytes,
archived validation and a probe report for AAC/32 kHz/2ch only. It is not
an audio-listening, visual-quality or latency acceptance. The A3 core supports
an injected transport, and the separate dry-run-by-default Stage B CLI has
passed offline code review. It still requires staged-byte verification,
runtime admission and explicit paid-window approval before any real
`/prompt` submission.

If prompt-bound progress is absent **before submission**, stop unless a
server-wall-only screen was separately authorized. If the observer loses
events **after an already authorized submission**, do not retry or
automatically cancel that prompt: retain valid history/graph/media as
`server_wall_screen_sampler_unknown` and stop follow-up work. Cancellation
belongs only to a separately approved cost/timeout contract. Neither this
offline runbook nor local fixture tests authorize a paid runtime check.

## Stop and interpretation

Stop before submission on any hash/graph mismatch, unexpected bypass,
missing source identity, unclear cache/concurrency, unbounded cost, or a
missing multi-GB model. Stop after one prompt; no automatic repeat. A
derived receipt supports at most a **single-sample deployment-combination
performance screen**, not a variance estimate, same-effect adoption,
production migration or cost parity. If required evidence cannot be
captured without modifying the production service, report `INCOMPARABLE`
and seek a separate observability plan rather than widening this run.
