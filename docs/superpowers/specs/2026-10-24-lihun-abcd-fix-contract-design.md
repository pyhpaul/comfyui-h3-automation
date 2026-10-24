# Lihun ABCD fix-contract design

Date: 2026-10-24  
Status: draft pending user review  
Context: Pilot `lihun-v23-pilot-abcd-1024` showed A solvable by cut; B/C/D failed a full seed round after pack surgery. Further same-structure seed batches are banned.

## Goal

Ship the four fail-class samples under a **RELAXED** contract that matches潮缚 fix standards: meaning-correct dialogue, correct speaker mouth on kept takes, editable garbage only in cuttable spans with `EDIT_NOTE`. Allow **wording / merge changes** to `（）` lines when story meaning is preserved.

## Non-goals

- Strict syllable-perfect match to original pack wording
- Second seed round on the same prompt structure
- Feiniu upload unless the user explicitly asks for this validation batch
- Switching H3 to a different base workflow for these four units (out of scope for this contract)

## Approach (selected)

**Per-class fix contract** (not “prompt tweak + hope”):

| Class | Unit | Strategy |
|---|---|---|
| A | EP57-U08 | Prefer cut; no rerender |
| B | EP11-U04 | Short silent action; one seed round; else cut speech / mute + bed |
| C | EP43-U06 | Audible short phrase or merge into neighbor; one seed round |
| D | EP19-U06 | Drop lone name beat; merge into next line; ≤2 seeds + frame review |

## Acceptance (RELAXED)

**Pass when all hold:**

1. Kept timeline has required dialogue **meaning** in order (wording may differ if approved merges/rewrites are in `prompt_source`).
2. Each kept spoken line is mouthed by the correct on-screen speaker; dual-shot: no chorus on kept takes (L2 watch required for EP43/EP19).
3. Ad-lib / swallow / garbled speech appears only in spans that can be cut entirely; `EDIT_NOTE.txt` lists cut points.
4. Proper-name near-miss (e.g. Ava≈Eva) may PASS if full-dialogue frame review confirms the intended speaker opened for that beat.

**Still FAIL (hard):**

- Missing required beat in the only kept take
- Wrong order of kept lines
- Chorus / wrong speaker on a kept line
- Garbled speech that cannot be cut without losing the only good take
- Anatomy/prop collapse that makes the shot unusable (escalate; do not “pass” via EDIT_NOTE alone)

## Per-class actions

### A — EP57-U08

- No pack change, no GPU.
- Ship existing C2 with cut `[0, 5.0)` and confirmed `EDIT_NOTE`.
- Before registry `shipped-relaxed`: one mouth check on 13.1–14.3s.

### B — EP11-U04 (silent / ad-lib)

Already done in pack: remove reading/whisper bed, Grace closed book + silent, duration 15.083→10.083, hard “no intelligible speech”.

Additional before GPU:

- If still long for action, target ~8s duration (action-complete minimum).
- Keep explicit ambient-only audio lock.

GPU: **one** batch of **4** seeds, new batch name, `--seed-offset` past prior seeds.

Stop-loss if all L1-fail with speech: **do not** second seed round. Cut audible spans or treat clip as silent picture + post ambient bed; `EDIT_NOTE`. If chorus/anatomy still blocks use → escalate outside this contract.

### C — EP43-U06 (short question)

Primary pack: `（Whose audience?）` with half-beat isolation (already applied).

GPU: **one** batch of **4** seeds.

Stop-loss if still swallowed: merge meaning into Tessa’s next line (e.g. Ava silent reaction; Tessa `（A judge is the audience, if it comes to that. …）`), delete standalone short-Q shot. No further seed round on the old short-Q structure.

### D — EP19-U06 (proper name)

Pack: remove standalone `（Ava.）`. Preferred clean structure: start from Ava’s proposal line; Damian answers with `（Say that slower.）` (name call absorbed or optional soft merge such as opening Damian on the slower-request beat only). Story keeps “call / propose / say slower / propose again / yes”.

GPU: **at most 2** seeds + mandatory frame review on the name-adjacent beats.

Stop-loss: Ava≈Eva with correct Damian mouth → RELAXED pass; else merge further or cut, not another seed stack.

## Shared rules

1. New Feiniu/local batch name every GPU attempt; never reuse prior seed offsets for the same job+prompt.
2. Pre-queue: `scripts/audit_pack_prompts.py --render-risk` exit 0; **no HIGH**.
3. Router: `fix_fail_router` — ban same-prompt ×N empty retries.
4. QC: L0 ∥ L1 (shared ASR) ∥ L3 (≥2fps + dense windows) ∥ L2 hard for dual-shot; `L2_blocks_close` if `WATCH_INCOMPLETE`.
5. Tick: `runs/visual_qc/<batch>/tick_status.txt` each plan refresh.
6. Shutdown only if user asked and queue empty + local artifacts complete.

## Validation plan

1. Apply remaining pack deltas (B duration trim if needed; D merge; C merge only after failed seed round or optionally pre-merge if user prefers zero short-Q risk).
2. Audit packs.
3. On user OK: GPU B×4, C×4, D×2 local download dir; A cut ship in parallel (no GPU).
4. One consolidated report: pass/fail per class, EDIT_NOTE paths, whether stop-loss fired.

## Open decisions (resolved in brainstorm)

- Success bar: **mixed RELAXED** (A cut; B/C/D must be listenable on kept takes; wording/merge allowed).
- Dialogue text need not match original pack character-for-character.

## References

- `docs/ops/2026-10-24-fix-flow-pilot-abcd.md`
- `docs/ops/2026-10-21-chaofu-fix-retrospective-and-standard.md`
- `docs/ops/2026-10-24-fail-prevention-and-vision-qc-workflow.md`
