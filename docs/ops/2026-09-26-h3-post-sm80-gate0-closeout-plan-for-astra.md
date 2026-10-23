# H3 post-SM80: Gate 0 closeout and conditional 5090 screen

Status: **Astra PASS for the zero-CU Stage A plan only**. The initial review
was CONDITIONAL; five blockers were corrected and the read-only re-review
found no remaining plan blocker. Stage A tooling has since been implemented
offline; see `2026-09-26-h3-gate0-implementation-result.md` for verification
and the remaining provenance boundary. Gate 0 is not yet closed. This plan
does not authorize a rental restart, Colab session,
model transfer, prompt submission, or quality adoption.

## Decision context

The archived RTX 5090 EP04-U02-v16 did run, but its U01 motion parent SHA-256
is `9131bac0...249376`, whereas the formal A100 U02 parent is
`6def89c0...5946a`. The historical 5090 646-656 s is client polling; there
is no correlated server/sampler receipt or submitted graph. The v19 5090
sample also has a different job and parent. See
`2026-09-26-h3-post-sm80-gate0-inventory.md`. Therefore **no existing
same-input 5090 sample can close the performance comparison**. The current
A100 Sage C1/C2 server/sampler pairs remain 1324.348/1208 s and
1322.164/1206 s; human quality acceptance remains deferred.

The near-term question is not whether to keep tuning A100 blindly. It is
whether a matched 5090 deployment is materially faster for the unchanged
workflow, and whether that difference is worth a separate quality/economics
decision. A single new 5090 sample can screen this question, not prove
intrinsic GPU superiority or production replacement.

## Stage A: finish Gate 0 offline (next executable work)

1. **Seal the comparison input.** Create a machine-readable, sorted manifest
   from the archived formal A100 preflight: six model/LoRA SHA-256 values,
   prompt source, four reference PNGs, deployed runner adapter and KJNodes
   source, the separate A100 U01 parent SHA-256, and C1 submitted-graph
   SHA-256. Record job/profile, seed, actual 12-step sigma slice, resolution,
   video/audio output contract, startup flags, ComfyUI and attention binary
   identities. Use the archived D: artifacts as source; do not regenerate
   from the dirty working tree. Give the manifest its own SHA-256.
2. **Implement a read-only comparator and receipt validator.** It accepts
   explicit archived graph/manifest/receipt paths and never calls `/prompt`,
   rewrites a job, downloads full outputs or restarts ComfyUI. The graph
   allowlist is only node 58 attention routing and nodes 264/400 output
   prefixes; compare all other nodes exactly, except the separately declared
   parent-path alias below. **Before normalization**, assert that the
   `rtx5090` graph contains node 58 with the Sage patch class and the exact
   model edge to node 128. An unexpected bypass fails even though the
   generic A/B normalizer accepts bypass graphs. Record the deployed SM120
   binary/source identity separately. Reject missing hash, changed parent,
   model, sampler, seed, LoRA, reference, resolution or unexplained graph
   diff as `INCOMPARABLE`, not as a slow/fast result. Reuse the existing
   `h3_a100_ab_contract.py` normalization only **after** profile and parent
   checks, with positive and negative fixtures; do not loosen it to force
   parity.
3. **Freeze one receipt contract.** Require environment identity
   (GPU/driver/clocks, Python/Torch/CUDA/Sage, ComfyUI/startup flags),
   input/model/source hashes, manifest ID, actual submitted graph and diff,
   process age/cold-warm/cache/concurrency state, correlated prompt/history,
   server and sampler wall, each of 12 executed steps, 5-second GPU/VRAM
   samples, setup/restore/transfer/backup wall, and new MP4/latent validation.
   Define a target-prompt execution interval, sampler node identity, one
   continuous 12-step sequence **inside that interval**, cached-node status
   and evidence of no interleaved task. The current `parse_step_timing()`
   collects step numbers from its entire input and must not be given a shared
   production log without prompt-isolated extraction. If isolation is not
   provable, report `INCOMPARABLE`; do not restart or patch production merely
   to create it.
   Missing required proof yields `INCOMPARABLE`. Record decoded video/PCM
   hashes and frame/audio count, cadence, timestamps and time bases using
   the existing media helpers; raw MP4 SHA differences alone do not imply
   generated content changes. Do not read the blind-review mapping.
4. **Fixture-test and dry-run.** Tests cover matching C1/C2/S1 archived
   graphs, an unexpected 5090 bypass, a changed parent, changed sampler/seed,
   unexpected node, missing 12-step proof, a shared-log splice that combines
   steps from different prompts, stale/foreign receipt, metadata-only MP4
   remux, and shifted media timestamps. Dry-run against existing A100
   receipts only; no GPU.
   If archived A100 data lacks a field, mark it `unknown` and disclose the
   limitation rather than backfilling an invented value.
5. **Review a conditional runbook.** Pin exact read-only preflight commands,
   expected hashes, output locations, timeout, maximum permitted transfer,
   cost estimate and stop procedure. The 34.6 MB A100 parent must **never
   overwrite** the existing production parent. If transferred, place it at
   a unique staging path. Node 401 `inputs.latent_path` may map only from
   `h3_context/ep04_u01_00001.safetensors` to that declared staging path;
   validate staged content against the frozen SHA-256, then canonicalize this
   sole path alias before strict graph comparison. No other node 401 input
   or path is allowlisted. Any missing multi-GB model requires a separate
   authorization, not automatic restoration.

Gate 0 exit requires a versioned manifest, strict tested comparator, receipt
schema/validator, offline dry-run, and reviewed runbook. **It does not require
or authorize a live 5090 sample.** The Stage A inventory/verification reads
only local archival files; no rental wake-up, paid-environment check or
transfer may be counted as zero-CU work. A fixture pass is not a live 5090
result. Disclose any missing A100 timing/cache fields before Stage B so a
later 5090 output cannot be mistaken for a comparable pair.

## Stage B: at most one conditional 5090 U02 performance screen

Admission only in an **already needed** rental-5090 window with the frozen
U02 job planned there. If no such window exists, stop after Stage A and
report `WAIT_FOR_WINDOW`; a standalone paid rental/sample needs a new
explicit cost/time authorization. Even in an already-needed window, obtain
authorization that specifically covers this fixed-A100-parent U02 submission,
its small parent transfer, telemetry collection, output writes and a bounded
cost/time allowance; the existence of the window is not authorization.
Before any submission, verify actual GPU,
the original team ComfyUI path/profile, disk lifecycle, free space, six
model hashes, source/graph identity and transferred A100 parent hash. Never
replace the provider's preinstalled ComfyUI with an unreviewed process, and
do not restart production solely to clear cache. Stop on hash/graph mismatch,
missing model, unclear concurrency/cache state, excessive transfer, or
unbounded rental cost.

If admitted, submit **one** production-profile `motion_latent`, one-pass,
12-executed-step EP04-U02-v16 using the frozen A100 U01 parent and the same
prompt/references/seed/models/LoRAs/resolution. Preserve new prompt ID,
actual graph, timestamped server log/history, each-step progress, 5-second
GPU telemetry, MP4, AV latent and verification receipt. Prove all 12 steps
executed in this prompt's interval and no cached sampler output was returned;
reject interleaved or stitched progress logs. Preserve full media at an
operator-approved destination and only small receipts to D; do not assume
the prior rental image, disk or Drive path persists. No automatic
retry, U03 continuation, A100 rerun, or blind-map access.

## Stage C: interpretation and stop conditions

- Report A100 and 5090 **server and sampler** wall with run dates, process
  state and deployment-specific attention implementations. One 5090 sample
  is a directional `performance screen only`, not a variance estimate.
- Keep setup/restore/transfer/backup and actual hourly/CU prices outside
  per-video generation time; cost-per-unit needs separate one-unit and
  multi-unit amortization. Historical Colab rates are not current prices.
- Human review of continuous picture **and audio**, plus an accepted
  same-input 5090 reference, gates any `same effect` or migration claim.
  The deferred A100 blind A/B review is not replaced by hashes or an agent's
  contact-sheet preference.
- If any decisive input, execution, cache or timing boundary is unknown,
  report `INCOMPARABLE` and stop; do not buy retries to manufacture a result.
  If the 5090 screen looks materially better, propose a **separate** Blackwell
  deployment/economics plan. If A100 remains a hard requirement, propose a
  **separate** mechanism-specific A100 investigation with a new budget and
  review; do not revive the rejected SM80 `launch_bounds` candidate.

## Astra review questions

1. Is Stage A the highest-value zero-CU step now, or is any additional
   offline evidence sufficient to avoid implementing a comparator?
2. Are the manifest, graph allowlist, receipt fields and `INCOMPARABLE`
   rules strict enough for a credible same-input screen without implying
   binary-identical SM80/SM120 execution?
3. Is the conditional Stage B admissible only with a planned rental window,
   or does it hide any unapproved cost, service mutation, quality downgrade
   or unnecessary model transfer?
4. What minimal fixture or live-run proof is missing before claiming that
   the zero-CU Gate 0 is actually closed?

## Review outcome

Astra accepted the corrected plan: profile-specific Sage node validation
precedes graph normalization; the A100 parent uses a hash-verified unique
staging alias without overwriting production; 12-step evidence is bound to
one prompt and sampler interval; Gate 0 can close offline; and an existing
rental window still requires explicit authorization for this exact sample
and bounded cost. The review was read-only and did not run either GPU.
