# MiniMax H3 official skills vs this repo’s pack prompts

Date: 2026-10-19  
Primary source: [MiniMax-AI/MiniMax-H3 `skills/`](https://github.com/MiniMax-AI/MiniMax-H3/tree/main/skills) (raw `README.md`, `h3-prompt-writing/SKILL.md`, `references/base-en.txt`, `references/ref-en.txt`)  
Pack sample: `jobs/ep_units/EP*-潮缚-*/assets/prompt_source.txt` (≈386 units; deep sample EP45/48/53/59/61–63)  
Standing constraints: `.cursor/rules/h3-*.mdc`, `.cursor/skills/comfy-h3-pack-prompt-audit/SKILL.md`

This note is for **prompt-improvement directions**. It does not authorize bulk edits to job packs, queueing, or commits.

---

## 1. Official skills inventory

From `skills/README.md`: **1 prompt-writing skill + 8 style generators**.

| Skill | Purpose | Relevant to photoreal short-drama (潮缚)? |
| --- | --- | --- |
| `h3-prompt-writing` | Rewrite into H3 structures for T2VA / I2VA / FL2VA / L2VA / Ref2VA; guides in `base-en.txt` + `ref-en.txt` | **Yes — primary reference** for dialogue IDs, `<d>`, soundscape, retention |
| `minimalist-product-ad-generator` | Clean e-commerce product ad shorts | No (product promo, not drama) |
| `3d-animation-short-generator` | End-to-end stylized 3D narrative animation | No (explicitly not photoreal live action) |
| `papercraft-stop-motion-explainer` | Handmade papercraft education explainers | No |
| `brand-promo-video-generator` | Brand / product / site promo with CTA | No (marketing, not serial drama) |
| `music-video-subtitle-generator` | Beat-synced MV + lyric typography | No (unless a rare MV-style insert) |
| `co-op-game-intro-generator` | Two-player game menu / opening animation | No |
| `paper-collage-explainer-generator` | Halftone paper-collage explainers | No |
| `handdrawn-live-video-generator` | Surreal hand-drawn overlays in live space | Marginal (single creative clip; not EP packs) |

**Takeaway:** For this repo, only `h3-prompt-writing` (+ its two reference guides) should drive pack-prompt changes. Style skills are orthogonal and should not reshape 潮缚 `prompt_source`.

---

## 2. Official prompt structure (what the guides actually require)

### 2.1 Base modes (`base-en.txt`) — T2VA / I2VA / FL2VA / L2VA

Ordered fields:

1. Optional keyframe instruction line (`<Picture N>` alignment) for I2VA / FL2VA / L2VA  
2. `integrated_multimodal_description:` — timeline shots `[Shot N]`, camera, speakers, dialogue, diegetic audio  
3. `overall_soundscape:` — ambience + physical + non-verbal human sounds only (no dialogue repeat)  
4. `non_diegetic_music:` — audience-only score, or `N/A`

**Dialogue rules that matter for us:**

- Stable speaker IDs: `(S1)`, `(S2)`, …; compound `(S1,S2)` only when they truly speak together  
- Spoken text only inside `<d>[Language] …</d>`; identity, action, and delivery stay **outside** `<d>`  
- Preserve dialogue words verbatim; do not translate  
- Voiceover: after `<d>`, explicitly say on-screen lips remain closed  
- Cut-crossing speech: `<scenetrans>` / continuity phrases; truncation: `<cutoff>`

### 2.2 Full-reference Ref2VA (`ref-en.txt`)

Six English sections in order:

`subject_definitions` → `summary` → `retention_analysis` → `detailed_description` → `overall_soundscape` → `non_diegetic_music`

Labels: `<Subject N>`, `<Picture N>`, `<Video N>`, `<Audio N>` with retention markers (`fully_preserved`, `partially_preserved`, `attribute_transfer`, `weak_reference`, audio `fully_copy` / `partially_copy` / `reference`).

Complete example shows the pattern we care about for two-speaker echo:

- Speaker tagged `(S1)` / `(S2)` at each vocal event  
- After a line: **“She closes her lips…”**  
- Listener is not given mouth-open / lip-sync cues while the other speaks  

### 2.3 Modes vs this pipeline

| Official mode | This repo’s usual path |
| --- | --- |
| Ref2VA six-section English rewrite | **Not used** for light 潮缚 packs; project forbids wholesale six-section rewrite |
| I2VA / FL2VA keyframe English body | Character/scene stills are bound as `<Picture N>` at wire/submit (`prompt_h3.txt`), but body stays Chinese pack structure |
| Continuity via `<Video N>` / audio reuse | Serial units use **motion_latent** + Chinese `【H3 latent 接入/交出/接力】`, not official Ref2VA `retention_analysis` |

Official Ref2VA is still useful as a **vocabulary source** (speaker IDs, lip-closed beats, soundscape split), not as a pack rewrite target.

---

## 3. Current 潮缚 `prompt_source` patterns (observed)

Typical section order (Chinese ops headers, not official field names):

1. `【H3 提示词】` / `【参考设定】` — characters with `@char-…` / `［char-…］`, scenes, props  
2. `【氛围与画质】` — photoreal + diegetic-only audio policy (“不加配乐和字幕”)  
3. English dialogue lock: “只能读（）内的英文” + often `【英文对白白名单｜硬锁】`  
4. `【空间／朝向硬锁】` — blocking, camera side, “对拍另一端…另一人在画面纵深或画外”  
5. `【画面内容】` — `▲` shots; dialogue as `口型同步开口…说：（ English. ）`  
6. `音频：环境音［…］+ 动作音［…］+ 人物音［…］`  
7. Optional latent blocks: `【H3 latent 接入文字】` / `【交出状态】` / `【H3 latent 接力文字】`

**Quantified on a 45-unit recent sample (EP45/48/53/59/61–63):**

| Signal | Approx. frequency |
| --- | --- |
| `口型同步开口` | almost all dialogue units |
| `另一人在画面纵深` (in space lock) | all sampled units |
| `英文对白白名单` | almost all |
| Chinese `音频：环境音…` | all |
| Official `overall_soundscape` / `integrated_multimodal` / `subject_definitions` / `retention_analysis` | **0** |
| Official `<d>` or `(S1)`/`(S2)` | **0** |
| `<Picture` / `<Video` in `prompt_source` | **0** (by design: bound into `prompt_h3.txt` at wire) |
| Speaker “说完，嘴唇合上/抿住” | common on **speaker** after their own line |
| Explicit **listener** 闭口 while someone else speaks in a dual-visible frame | rare; many dual-visible ▲ lines lack it |

High-risk shape already called out in pack-audit skill and `docs/ops/2026-10-17-dialogue-gate-burn-avoidance.md`:

> `口型同步开口` + named second person / depth other + **no listener lips-closed lock** → H3 lip-ownership crosstalk (both mouths follow one line). ASR dialogue gate usually **misses** this.

Concrete dual-visible examples:

- EP45-U01 ▲: Victor speaks while Sienna (and Danny) share a medium two-shot — no “Sienna 嘴唇合上/闭口无声” on that beat  
- EP48-U01 ▲: Cole speaks with Victor in background doorway — speaker closes lips after; Victor’s mouth during Cole’s line is unlocked  
- EP48-U01 ▲: Victor speaks OTS with Sienna in frame right — same gap  

Positive adjacent patterns already in packs (keep):

- Whitelist + “说完后绝对静音 / 禁止口型” (tail junk mitigation)  
- `［画面说明·禁读·禁止口型］` on silent action beats (when present)  
- 对讲机 / off-screen voice (e.g. EP62-U02): voice from radio without forcing the on-screen listener to lip-sync the radio line — aligns with official VO “lips remain closed” intent  
- Money digitization / lengthened greetings from prior burn-avoidance work  

---

## 4. Gap analysis (official vs pack)

| Official expectation | 潮缚 pack today | Gap severity | Compatible with unpack/audit/runner? |
| --- | --- | --- | --- |
| `(S1)`/`(S2)` stable speaker IDs | Character names + `口型同步开口` only | **High** for two-speaker echo | Yes — additive next to names; keep `（）` for gate |
| Dialogue in `<d>[English] …</d>` | Fullwidth `（ text ）` | Medium (model may prefer `<d>`; gate/ASR keyed to `（）`) | **Do not replace wholesale**; optional dual-mark only if experiments justify |
| Listener / VO lips closed | Speaker post-line “嘴唇合上” common; co-visible listener rarely locked | **Highest** | Yes — one Chinese clause per dual-visible ▲ |
| `overall_soundscape` + `non_diegetic_music: N/A` | Chinese `音频：…` + “不加配乐” | Low–medium | Optional mirror line; do not delete Chinese audio line |
| Shot timestamps `[Shot 2] At 00:03.500` | Unnumbered `▲` beats inside ~15.083s | Low (packs already timed by beat count) | Leave; do not force English shot clock rewrite |
| Ref2VA `retention_analysis` / six sections | Latent 接入/交出/接力 Chinese | Intentional fork | **Non-goal** to convert packs to Ref2VA English |
| `<Picture N>` / `<Video 1>` consistency | In wired `prompt_h3.txt`, not raw `prompt_source` | None if audit passes | Keep wire path; audit remains the gate |
| Action + delivery outside spoken payload | Action prose already outside `（）` | Low | Align combat/action LoRA tests with this split |

Project rules that **override** naive “follow official rewrite”:

- Keep pack body; only allowed structural body edits are media labels, four-grid→single-panel wording, second camera→画外  
- Do **not** require six-section English `subject_definitions…`  
- Keep Latin dialogue as `（ text ）` (inner spaces); do not rewrite English words  
- Continuity default: `motion_latent`, not whole-film `ref_video`, unless user says so  

---

## 5. Prioritized improvement directions

### P0 — Dialogue / two-speaker echo (minimal pack edits)

**Goal:** Reduce dual-mouth echo without fighting audit or ASR.

1. **On every dual-visible dialogue ▲** (two faces, OTS with face + shoulder, speaker + depth other):  
   - Speaker: keep `口型同步开口` + `（ line ）` + after-line `嘴唇合上`  
   - Everyone else in frame: `嘴唇合上，闭口无声，禁止口型` for that beat  
   - Explicit ban: `禁止两人同念同一句`  
2. **Optional speaker IDs** (official-aligned, still Chinese body):  
   - First vocal event: `Victor Harlow（S1）…说：（ … ）`  
   - Next distinct speaker: `（S2）`  
   - Do **not** invent `(S1,S2)` unless the pack truly wants unison  
3. **Do not** convert `（）` → `<d>` in bulk until a controlled A/B shows gain **and** `dialogue_gate.extract_expected_dialogue` is updated  
4. Pre-queue: flag missing listener-lock as **high risk** (warn); do not auto-FAIL wiring audit  
5. Post-Feiniu: spot-check 1–2 dual-visible units per EP first (existing policy)

**Suggested one-line inject (Chinese, localizable):**

```text
本镜说话者开口时，画面内其他所有人嘴唇合上、闭口无声、禁止口型；禁止两人同念。
```

Place once under the dialogue lock block, and/or inline on risky ▲ lines.

### P1 — Combat / action LoRA testing (action→dialogue, triggers)

No combat-specific LoRA is documented in this repo’s pack tree; graph still carries general LoRAs (e.g. MysticXXX strength knobs in HANDOFF). For **any** action/combat LoRA A/B:

1. **Isolate variables:** one LoRA strength / trigger set per trial unit; keep motion_latent chain rules unchanged  
2. **Action → dialogue order (official-aligned):** in the same ▲, write visible action and camera **before** `口型同步开口` / `（）`; never put fight choreography inside the spoken parentheses  
3. **Triggers:** keep LoRA trigger tokens in visual/action prose (outside `（）`), never inside dialogue whitelist lines  
4. **Lip ownership still applies:** during punches/grapples with two faces visible, lock non-speakers’ mouths even harder — motion LoRAs often increase mouth jitter  
5. **Soundscape:** put impacts / fabric / breath in `音频：动作音／环境音`; keep `人物音` only for real lines; keep `non_diegetic` off (packs already say 不加配乐)  
6. **Success criteria for a trial:** (a) choreography readable, (b) whitelist lines intact under spot-check, (c) no dual-mouth echo, (d) latent handoff still clean — before scaling strength across an EP  

### P2 — Soundscape / retention vocabulary (light touch)

1. Optionally append an English mirror under the existing Chinese audio line, only when experimenting:

   ```text
   overall_soundscape: <one English sentence of ambience + foley; no dialogue>
   non_diegetic_music: N/A
   ```

2. Treat latent 接入/交出 as this project’s **retention** channel; do not add full `retention_analysis` blocks to light packs  
3. For 对讲机 / phone / VO: copy official VO rule in Chinese — `画内角色嘴唇保持闭合` while the device speaks  

### P3 — What “official six-section” would mean here (and why not)

A full Ref2VA English rewrite would map roughly:

| Official section | Nearest pack analogue |
| --- | --- |
| `subject_definitions` | `【参考设定】` + wired `<Picture N>` |
| `summary` | scene/人物 lines under `【画面内容】` |
| `retention_analysis` | latent 接入/交出 (+ parent video only if `ref_video`) |
| `detailed_description` | `▲` 因果正文 |
| `overall_soundscape` | `音频：环境音+动作音` |
| `non_diegetic_music` | “不加配乐” → `N/A` |

**Do not** auto-convert packs to that English six-pack: audit skill and `h3-pack-prep` forbid it; language is not the quality lever; media wiring + intact causal text is.

---

## 6. Explicit non-goals

- Bulk rewrite of `prompt_source` to English six-section Ref2VA / T2VA templates  
- Replacing `（）` dialogue with `<d>` across the catalog without gate + A/B proof  
- Changing continuity default from `motion_latent` to whole-film `ref_video`  
- Turning on `--dialogue-gate` by default (still user-opt-in / spot-check driven)  
- Editing English dialogue words, inventing new plot beats, or “summarizing” ▲ shots  
- Applying the 8 style-generator skills to 潮缚 EP packs  
- Queuing renders or committing as part of this research note  
- Treating disk `prompt_audit.json` alone as preflight (still must run `scripts/audit_pack_prompts.py`)  

---

## 7. Agent checklist — next pack audit

Use with existing `comfy-h3-pack-prompt-audit` procedure; this list only adds official-skill-aligned prompt quality checks.

- [ ] `python scripts/audit_pack_prompts.py` → PASS (no_parent **and** with_parent); no `FAIL latent-scene`  
- [ ] Body kept; labels only `<Picture N>` / `<Video 1>` where wired; no six-section English rewrite  
- [ ] Latin dialogue remains `（ text ）` with inner spaces; whitelist matches spoken lines  
- [ ] **Dual-visible dialogue:** every such ▲ has listener 闭口/无声; flag high risk if only `口型同步开口` + 纵深/画内他人  
- [ ] Optional: stable `（S1）`/`（S2）` on multi-speaker units (same ID across the unit)  
- [ ] Silent / action-only ▲ marked 禁读·禁止口型 when present; tail silence after last line  
- [ ] VO / 对讲机 / phone: on-screen mouths closed while device speaks  
- [ ] `音频：` has ambience/foley; dialogue not duplicated as ambient; no BGM unless intended  
- [ ] Action/combat LoRA trials: triggers + choreography outside `（）`; action before speech; lip locks still present  
- [ ] After Feiniu: spot-check 1–2 dual-visible units for two-speaker echo before considering dialogue-gate  

---

## 8. Source pins

- Skills tree: `https://github.com/MiniMax-AI/MiniMax-H3/tree/main/skills`  
- Raw README: `https://raw.githubusercontent.com/MiniMax-AI/MiniMax-H3/main/skills/README.md`  
- Raw skill: `…/skills/h3-prompt-writing/SKILL.md`  
- Raw guides: `…/skills/h3-prompt-writing/references/base-en.txt`, `ref-en.txt`  
- Local related ops: `docs/ops/2026-10-17-dialogue-gate-burn-avoidance.md`  
- Audit skill: `.cursor/skills/comfy-h3-pack-prompt-audit/SKILL.md`  
