# Test2 EP02/EP03 offline admission audit

This is an offline review of the 2026-09-25 static H3 call pack, not a Colab
production receipt. No paid runtime was started and no EP02/EP03 job is approved
for submission yet. The source ZIP is immutable; all future corrections belong
in separately named derived jobs.

## Source and checks completed

- Source: `C:\Users\lxy\Downloads\海外短剧测试2-H3静态调用包-EP01至EP03-20260925.zip`.
  SHA-256: `9927f713bebff146ff10f51e7311df8e32a55e1eb3ae422a2ba832c1c4029ef0`.
- `unzip -tqq` passed. EP02 has seven units and EP03 has eight. Their 34
  unique PNG assets decoded with FFmpeg. Every `upload_order.absolute_path`
  resolves to a packaged asset after removing the source Windows prefix.
- For all 15 units, the `@char-*`, `@scene-*`, and `@prop-*` tokens in the
  prompt match the manifest's uploaded ID set and count exactly. Stage them
  strictly in manifest `upload_order`; image reference counts are 3-9 per
  unit, and none exceeds nine.
- Both manifests still say `built_pending_validation`, `submission=not_done`,
  and `av_acceptance=not_evaluated`. Their existing owner acceptance covers
  source staging, not ComfyUI graph admission or generated-video quality.
- The packaged scene plates are four-view sheets (1672x941). The motel,
  rental-room, day-hall, night-hall, and hospital plates were visually
  inspected; their depicted spaces are plausible for the scripted settings.
  This does not prove H3 will avoid four-grid rendering. Do not crop a plate
  without a specific single-camera/landmark match and a derived-job record.
  The motel U02 asks for both the south door and the east bedside lamp in one
  sequence, while the scene sheet separates those views; its first render
  needs an explicit no-split-frame check.

The packaged `E:\...` paths are not runnable on Colab. The current
`scripts/ep_pack_to_jobs.py` recognizes an older `manifest.csv` manual-call
format, not these `package-manifest.json` deliverables. The EP01 production
contract and phase code are EP01-specific, so renaming the episode would not
be a valid EP02/EP03 admission test.

## Local derived artifacts and static verification

The one-off, pack-specific staging under `.scratch/` is not a new generic pack
converter. It generated 15 source-derived jobs and three separately named
EP02 independent-cut candidates. The selected 15-job archive uses those three
candidates plus the other 12 source jobs. For U02/U04/U06, source-to-candidate
diffs remove only the old-scene one-second overlap, parent latent and old
camera/position clauses; the new-scene `【画面内容】` lines and dialogue compare
identically after ignoring blank lines. Original full TXT bytes are retained
as `assets/prompt_pack_full.txt` in every job.
On 2026-09-28 the user accepted these three independent-start candidates as
the intended EP02 production input; this does not authorize a paid Colab
assignment or waive runtime and visual gates.

The offline graph check exposed a previously hidden six-image API limit:
`workflow_ui.json` displayed nine H3 image inputs, but the actual API
template, bindings and manifest schema only supported six. The local branch
now binds `ref_image_6..8` to three new `LoadImage` nodes, wires all nine
`<Picture N>` labels, and prunes unused new nodes for old six-image jobs.
This is a local code change, not a claim that the remote Colab copy is patched.
The 15 selected jobs passed local schema/file checks, prompt wiring and
one-pass graph-edge checks (including exact image count, Save/Load/Trim,
12 steps and 24 fps). The focused regression set passed 52 tests. No ComfyUI
runtime or GPU execution was part of these checks.

Frozen local candidate archives:

- Jobs: `/mnt/d/comfyui-h3-backups/rental-20260924-5090/test2-ep02-ep03/offline-20260928/test2-ep02-ep03-selected-jobs-v1.tar.gz`;
  SHA-256 `d73ff9de1137601d3625a90cdb2842cbfbb32e29208a963700d1611434e083ab`.
- API-nine patch: `/mnt/d/comfyui-h3-backups/rental-20260924-5090/test2-ep02-ep03/offline-20260928/test2-ep02-ep03-runtime-api9-v1.tar.gz`;
  SHA-256 `4c774aa0f6299ad2142712bf1b47845ea0f4ef567a890ad41f6603beb80b4a63`.

These archives are **candidate inputs**, not production receipts. The user
accepted the three independent starts, and the selected jobs archive was
uploaded once to
`h3drive_h3:comfyui-h3-colab-dedicated/standard-v1/inputs/test2-20260925/ep02-ep03/accepted-v1/test2-ep02-ep03-selected-jobs-v1.tar.gz`.
The local and Drive-side MD5 both equal
`49da02d2f7f7391c5708710e4100a20c`; Drive reports 200146604 bytes,
matching the local file. This is transfer-integrity evidence, not a remote
SHA-256 computation. The frozen input record is
`docs/ops/drive-test2-ep02-ep03-v1.json`. Do not re-upload this archive for
each Colab assignment. At the pre-upload check, Drive had 5451603350025
free bytes; Colab showed 117.62 CU, 0.00 CU/hour and no active assignment or
session. No paid runtime was started for this audit.

## Continuity decision by unit

`candidate` below means the intended derived-job topology, not a passed
graph or approved render. Keep the 15.083-second, 24-fps, 9:16, one-pass EP01
quality baseline unless a separate A/B test is approved.

| Unit | Scene | Refs | Source parent | Derived topology candidate | Critical output check |
| --- | --- | ---: | --- | --- | --- |
| EP02 U01 | hall day, lights off | 9 | none | independent | Re-anchor wedding state against EP01 ending; ring and cup positions. |
| EP02 U02 | motel night | 4 | U01 | **independent cut** | Enter motel immediately; door/chain/lamp action and dialogue. |
| EP02 U03 | motel night | 4 | U02 | U02 latent | Lamp remains below bed, Grant prone, Claire at bed edge. |
| EP02 U04 | rental room day | 3 | U03 | **independent cut** | Enter rental room immediately; cup and promise dialogue. |
| EP02 U05 | rental room day | 3 | U04 | U04 latent | Officer takes Sean; cup and door state persist. |
| EP02 U06 | hall day, lights off | 9 | U05 | **independent cut** | Return to wedding immediately; two cups, veil, ring, confession. |
| EP02 U07 | hall day, lights off | 8 | U06 | U06 latent | Sean rises without picking up the ring. |
| EP03 U01 | hall day, lights on | 9 | none | independent | Lighting/state re-anchor after EP02 U07; Helen enters. |
| EP03 U02 | hall day, lights on | 8 | U01 | U01 latent | Glass breaks; Helen's hand and bag remain distinct. |
| EP03 U03 | hall day, lights on | 9 | U02 | U02 latent | Shoe leaves hand; Sean blocks Claire. |
| EP03 U04 | hall day, lights on | 9 | U03 | U03 latent | Hospital reference appears only within phone screen, not as a full-scene cut. |
| EP03 U05 | hall day, lights on | 9 | U04 | U04 latent | Two goons, Grant, Helen and Briggs remain distinct through dense action. |
| EP03 U06 | hall day, lights on | 9 | U05 | U05 latent | Goon B restrains Helen; goon A stays injured. |
| EP03 U07 | same hall, night variant | 9 | U06 | U06 latent **trial gate** | One-second day tail then night cut; positions and absent refs survive. |
| EP03 U08 | same hall, night | 9 | U07 | U07 latent | Night state and restrained Helen persist; no extra entrance. |

EP02 U02, U04, and U06 cross from scene 002 to 003, 003 to 004, and
004 to 002 respectively. The current project pack-audit skill treats a
cross-place latent chain as a hard stop. Their source prompts explicitly ask
for one second of old-scene latent before a hard cut. A derived independent
start must therefore also remove or rewrite those old-scene/latent clauses;
changing only `parent_unit_id` would produce contradictory instructions.
Preserve the new-scene beats and original dialogue, record a semantic diff,
and obtain review before freezing. As with EP01 U05, a direct edit cut between
the two verified unit MP4s can preserve the narrative transition without
forcing old-scene context into the new shot.

EP03 U07 is different: `scene-002-S02` and `scene-002-S03` are the same hall
with a lighting/time change. The supplied day/night plates share the hall
layout, and the prompt explicitly requires a one-second day tail followed by
the night cut. Keep latent as the first candidate, but do not assume the
model will obey the hard cut. Its first render is a stop/go visual gate before
submitting U08. U07 demotes Helen and goon B from the nine still-image slots,
while their actions remain important; continuation quality is especially
dependent on the U06 latent. U04 also uses a second scene plate for the
hospital image inside a phone; prevent it from becoming a full-screen scene.

## Remaining gates before production submission

1. The accepted archive is already on Drive with matching size and MD5; do
   not upload it again. After a separately authorized paid instance starts,
   but before any unit submission, verify that the restored runtime has
   the API-nine patch; the historical Drive snapshot predates it. Check the
   active ComfyUI node contract for nine image inputs and run a no-queue bind
   on that instance.
2. Freeze a unit-level receipt and stop/reconcile policy. In a paid session,
   submit one unit at a time with an explicit verified parent path or no
   parent at the four independent EP02 starts and EP03 U01. Do **not** pass an
   entire episode to `run_ep_units_profiled.py --units`: its in-memory latent
   carries into the next unit without consulting the selected job's
   `parent_unit_id`, which would silently reconnect the three EP02 cuts.
   Inspect the submitted graph's LoadLatent edge before queueing. After any
   CLI WebSocket/404/401 failure, check
   server assignment, ComfyUI history, and output receipt before same-session
   reconnect or retry; never infer that the paid VM stopped from local CLI
   pruning. Do not restore the 38.79-GiB model set twice while the original
   assignment is still alive.
3. On first renders, inspect EP02 U02/U04/U06 cuts, EP03 U04 phone-screen
   framing, U05/U06 character separation, and U07 day/night cut before
   continuing dependent units. Archive each unit's MP4, raw AV latent, graph,
   telemetry, timing, and Drive receipt. Assembly must not trim child MP4s
   a second time if MotionContextTrim already removed their overlap.

The EP01 evidence establishes technical feasibility on an assigned G4, not
future GPU availability or visual acceptance of these 15 new units. Based on
EP01's measured per-unit and restore times, a single successful G4 session
for both episodes is a planning estimate of roughly three hours and 25-30 CU;
retries, changed graphs, and quality rerenders are outside that estimate.
