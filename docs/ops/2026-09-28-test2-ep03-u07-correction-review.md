# Test2 EP03 U07 correction review (offline, not approved for generation)

## Observed failure

The delivered U07 has 340 frames at 24 fps (14.166667 s). A one-frame-per-second
sheet shows Sean, Grant, Claire and Riva at the wedding table for roughly its
first nine seconds; only the final roughly four seconds return to the U06
floor-restraint state. U06 ends with goon B restraining Helen. U07's submitted
graph did load `h3_context/ep03_u06_00006.safetensors` and used
`MiniMaxH3MotionContext(context_length=22, audio_context_length=24)` followed
by `MiniMaxH3MotionContextTrim(match_tail=true, fps=24)`. Thus the observed
problem is not proven to be a missing parent latent. The original prompt asks
for 24 frames of day-tail replay, while the delivered child trims the overlap;
review the *assembled* U06/U07 boundary rather than expecting a full replay
second at the start of standalone U07.

## Frozen source and proposed controlled candidates

Do not mutate the accepted archive or its receipts. Derive a new U07 revision
from `EP03-test2-v1-U07`, with U06's verified parent latent and U08 left
unchanged until U07 passes. Preserve both original English dialogue lines
(`Vivian Locke.` and `Open your eyes. She's not standing in that doorway.`),
all named characters, the phone-screen-only Maya, the LOCKE card, the night
lighting, and the specified final positions.

1. **Candidate A - chronology only.** Keep all nine original image bindings.
   Clarify that the 22-frame MotionContext overlap reconstructs the U06
   restrained-Helen tail, is trimmed from the delivered child, and that the
   first *delivered* U07 frames must show the same people and positions after
   the day-to-night cut. Move the floor-restraint/Briggs/phone state ahead of
   wedding-table reaction shots in the shot order. Keep the remaining story
   beats and dialogue in their original order. This tests prompt timing while
   holding image references constant.
2. **Candidate B - reference rebalance, only if A fails.** Starting from A,
   replace two low-priority object stills with the already accepted Helen and
   goon-B character references from U06. Retain scene and LOCKE-card stills.
   The nine slots would be Sean, Grant, Claire, Riva, Briggs, scene S03,
   Helen, goon B, and LOCKE card. Veil and glass remain text-described.
   This tests whether missing restraint actors contribute to the failure;
   it does not prove causation if other model behavior changes.

| Candidate B asset | Source | SHA-256 |
| --- | --- | --- |
| Helen | `EP03-test2-v1-U06/assets/id3-char-014-w01.png` | `7a5da173070033d82975edc422eebda15ddf31fe510366115ac0fdae70dc7180` |
| Goon B | `EP03-test2-v1-U06/assets/id5-char-017b-w01.png` | `5f40fbb1f632d498d0bb07b37ed5c9cf2ed3eaa51f60e8add499ad1d3f323944` |

Both paths above are relative to
`.scratch/test2-ep02-ep03-selected/jobs/ep_units/`. The source U07 slots to
replace in B are `id6-prop-003-s01.png` (veil) and
`id7-prop-004-s01.png` (glass); preserve slot 8's LOCKE card. Update both
`job.yaml` image paths and the `<Picture N>` references in its actual prompt;
a path-only swap would mislabel the images and is not a valid candidate.

## Paid-run gate and acceptance

No G4 assignment, Drive upload or generation is authorized by this review
document. Before a paid run, freeze each candidate's prompt, nine image
hashes, job YAML and parent-latent SHA-256, and run no-queue binding/graph
preflight. On one G4 assignment, restore models once, submit U07 A, inspect
remote success/MP4/latent receipts and a 1 fps sheet. Submit B only if A
fails and the spending authorization covers another U07. Do not rerun the
unchanged fixed-seed source job.

An acceptable U07 must join U06's restraint state without a wedding-group
cold open, transition to the intended night state after the overlap, keep
Helen and goon B visible/consistent through the required shots, preserve the
two dialogue beats and finish in a state suitable for U08. If one candidate
passes, run U08 from *that* verified latent, inspect the joint boundary,
then reassemble EP03 under a new version. A passed sparse-frame check is not
full human visual or audio acceptance. Keep the assignment alive for
recoverable script/CLI errors, but reconcile uncertain remote submissions
before retrying. Record per-stage time, GPU samples, CU, artifact hashes,
Drive delivery and stable post-stop zero-assignment state.

The earlier U07+U08 phases totaled 1544.27 s (25.74 min); each additional
U07 candidate would add roughly one previous-U07 phase (772.12 s) if runtime
conditions repeat. A new session also needs model restore and setup, so
these are workload measurements, not a total-cost promise.
