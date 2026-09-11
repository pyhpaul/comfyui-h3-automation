# EP Pack → MiniMax H3 R2V Prompt Design

**Date:** 2026-09-09  
**Status:** Approved (delivery order C; converter route C — rule skeleton first)

## Goal

Convert Seedance-oriented EP unit prompt text into MiniMax H3 Reference-to-Video (R2V) six-section English prompts that match YZ slot wiring. Validate with a hand-written EP03-U01 gold prompt and one re-run before deciding on LLM polish.

## In scope

- Hand-written EP03-U01 gold H3 prompt aligned to YZ slot indices
- Deterministic rule converter: EP text + media slots → H3 six-section prompt
- `ep_pack` writes converted `fields.prompt`; keep EP source as `assets/prompt_source.txt`
- Rebuild U01 job, queue, pull, compare against prior Seedance-verbatim run

## Out of scope (this pass)

- LLM polish / rewrite
- Changing YZ graph topology, LoRA stack, or sampler steps
- Full-episode batch generation
- Changing control/previz media wiring (keep current slots; fix roles in text)

## Slot / label contract

Matches existing `map_yz_media_slots` / YZ H3 node wiring:

| Slot | Asset | Prompt label | Role |
|------|-------|--------------|------|
| `ref_image_0` | control | `<Picture 1>` | Storyboard / blocking only; never render markers/UI/color blocks |
| `ref_image_1..N` | identities | `<Picture 2..>` → `<Subject 1..>` | Character/scene identity, `fully_preserved` |
| `ref_video_0` | previz | `<Video 1>` | Timing, movement, camera only; ignore low-poly look |
| — | — | `non_diegetic_music` | Always `N/A` (EP forbids BGM) |

## Converter behavior

**Input:** raw EP `prompts/Uxx.txt` + resolved media slot paths.  
**Output:** single English string with sections in order:

1. `subject_definitions`
2. `summary`
3. `retention_analysis`
4. `detailed_description`
5. `overall_soundscape`
6. `non_diegetic_music`

**Extraction:** Drop upload metadata, path lists, Seedance `@` upload rules. Keep atmosphere, timed shot bodies, and infer diegetic SFX.  
**English:** Template + light literal phrasing (structure over literary quality).  
**Artifacts:** `job.yaml` `fields.prompt` = H3 text; `assets/prompt_source.txt` = EP original; `assets/prompt_h3.txt` = same as job prompt.

## Acceptance

- Converter output for U01 shares structure and label indices with gold (wording may differ)
- Re-run completes; artifacts under `outputs/<job_id>/` and Downloads side-by-side with prior run
- Human judges visual quality vs prior Seedance-verbatim clip before any polish layer

## Non-goals for v1 quality

Perfect bilingual rewrite; matching gold wording exactly; automatic shot-time parsing beyond EP section headers.
