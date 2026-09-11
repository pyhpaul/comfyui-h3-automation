# YZ H3 slot ↔ prompt label wiring

Must stay consistent with `map_yz_media_slots` and `MiniMaxH3ReferenceToVideo` input order.

| Job field | YZ UI title | H3 label | Role in prompt |
|-----------|-------------|----------|----------------|
| `ref_image_0` | YZ控制图 | `<Picture 1>` | Storyboard / blocking only; never render markers/UI/color blocks |
| `ref_image_1` | YZ参考图1 | `<Picture 2>` → `<Subject 1>` | Identity fully_preserved |
| `ref_image_2` | YZ参考图2 | `<Picture 3>` → `<Subject 2>` | Identity fully_preserved |
| `ref_image_3` | YZ参考图3 | `<Picture 4>` → `<Subject 3>` | Scene/env fully_preserved |
| `ref_image_4..5` | YZ参考图4–5 | `<Picture 5..>` | Extra identities if present |
| `ref_video_0` | YZ参考视频 | `<Video 1>` | Timing / motion / camera only; ignore whitebox look |

## Prompt shape

**Preferred (EP02 causality / H3-ready TXT):** keep pack text; only wire media names via `prompt_wire` → see `comfy-h3-pack-prompt-audit`.

**Legacy converter output (optional):** six sections, often English body:

1. `subject_definitions`
2. `summary`
3. `retention_analysis`
4. `detailed_description` with `[Shot N]` / timestamps
5. `overall_soundscape`
6. `non_diegetic_music` → `N/A` for EP packs (no BGM)

Language (EN vs ZH) is **not** treated as a quality gate anymore.

## Anti-patterns

- Pasting Seedance `@char-001` / pack paths into H3 prompt
- Assuming EP `upload_order` index == H3 `<Picture N>` (control is always Picture 1 in YZ)
- Expecting `/prompt` to refresh the Comfy canvas (need bound UI Load)
