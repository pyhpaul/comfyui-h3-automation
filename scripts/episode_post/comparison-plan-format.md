# Independent comparison plan fields

`run_episode_comparison.py` reads a neutral shared input contract plus an agent's
own JSON decision plan. Do not use another agent's filled plan as your starting
point if the goal is independent comparison.

Required fields:

- `agent_id`, `revision`, `shared_input_sha256`: identity and exact contract digest.
- `clips`: ordered `{unit,in_frame,out_frame,reason}` entries; frame bounds are
  half-open. Keep all four units in story order and required scripted dialogue.
- `protected_ranges`: `{unit,in_frame,out_frame,reason}` action/dialogue intervals
  that no chosen source trim may remove.
- `subtitle_aliases`: explicit ASR name aliases only, never invented dialogue.
- `subtitle_style`: font_size/outline; optional `end_overrides` keyed by exact
  canonical phrase, and `line_breaks`. End overrides use this plan's output seconds.
- `zh_captions`: required Chinese phrase list, same order/count as displayed
  English cues after alignment. Timing is copied from the English track; this is
  the delivered Chinese word track (`{EP}.zh.srt` / `{EP}.zh.ass`). Packs that
  only have English in `（）` must supply translations here.
- `music.cues`: `{start,end,source_in,target_lufs_before_duck,fade_in,fade_out,reason}`.
  The engine measures each excerpt independently, then applies speech ducking.
  BGM is mixed into `*-review-en.mp4` only; `*-master.mp4` is dialogue + ending
  SFX with no BGM bed.
- `ending`: `{preset_id,preset_version,sfx_gain_db,reason}`. Current renderer only
  implements `bloom-hold-suspense` v1. Choosing another structure requires a
  separately validated renderer adaptation and an explicit engine-change note.
- `review_notes`: actual editorial risks and inspection limits.

Additional narrative intent, rejected alternatives and exposure to prior runs
should be recorded. The engine records source/skill identities and its own file
hashes; it does not infer creative quality from those hashes.

Current technical contract remains 24fps/768x1376/English and the same single
licensed music asset. Whole-episode normalization uses -16LUFS with extra peak
headroom, then checks encoded output against the shared -1.5dBTP ceiling.

Run final-export ASR and `verify_ep_post_pilot.py` afterward, then self-review
sound, visuals/subtitles and story against the actual final hash. Independent
subagent review is disabled by default and runs only when explicitly requested.
