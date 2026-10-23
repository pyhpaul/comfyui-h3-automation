# EP17/EP18 wenwu-test packs — official MiniMax H3 skill prompt scan

Date: 2026-10-20
Official source: MiniMax-AI/MiniMax-H3 `skills/h3-prompt-writing` (SKILL.md +
`references/base-en.txt` + `references/ref-en.txt`), cloned 2026-10-20.
Subjects: `jobs/ep_units_wenwu_test/EP17-兽王降临-wenwu-U01..U08`,
`EP18-秘银碎裂-wenwu-U01..U08` (16 units, all 12.0s).
Standing constraints: `.cursor/rules/h3-pack-prep.mdc`,
`.cursor/skills/comfy-h3-pack-prompt-audit/SKILL.md`,
`docs/ops/2026-10-19-minimax-h3-official-skills-vs-pack-prompts.md`.
This scan reports only; no prompt body was edited by it.

## Already fixed before this scan (allowed edit classes only)

- EP17-U08: scene-037 + scene-035 fourgrids cropped to the 东→西 panel
  (camera stays on the east side for the whole descent); fourgrid sentences
  rewritten to single-panel wording; full grids backed up outside `assets/`.
- EP18-U05: scene-038 cropped to 南→北 (dead-angle camera faces the north
  wall / east arch), scene-035 cropped to 南→北 (arena segment tracks Cain
  toward the north stand base); same sentence treatment.
- Re-ran `scripts/audit_pack_prompts.py` on both jobs: PASS, exit 0.

## What already matches the official skill

- Dialogue payload only inside `（ … ）`, action/delivery prose outside it;
  in every dialogue shot the choreography is written before `口型同步开口`
  (official action→speech order).
- Every unit has an `音频：` soundscape line (ambience + foley + real voice
  only) and `无配乐` — equivalent to `overall_soundscape` +
  `non_diegetic_music: N/A`.
- Reference retention is carried by `【H3 latent 接入文字】/【交出状态】`
  (the project equivalent of Ref2VA `retention_analysis`); `<Picture N>`
  wiring happens in `prompt_h3.txt` and passes preflight. Converting these
  packs to the English six-section Ref2VA format remains a non-goal.
- Fight choreography names contact points and end states per shot (official:
  "the points where referenced content actually appears"), e.g. EP17-U01
  palms-to-steel-jaw, EP18-U04 sword snap + knee strike.

## Findings (prioritized)

### P1 — Co-visible listener has no lips-closed lock (2 shots)

Official guides: stable `(Sx)` IDs, and after/around a line the non-speaker
keeps lips closed (this repo's known two-speaker echo risk).

- EP18-U03, Cain's line `（Impossible! …）`: Liam is co-visible in the
  double mid-close ("Liam 的站位和夹刃姿势保持稳定") but his mouth is never
  locked. Add one clause: Liam 嘴唇合上、闭口无声。
- EP18-U08, Liam's line `（Lord Vane! …）`: Cain's face is visible in the
  mud under Liam's foot in the same frame; no lock on Cain's mouth.
- Already good, keep as the pattern: EP17-U03 (`Liam说完，嘴唇闭合`),
  EP17-U07 (Vane `嘴唇紧闭，没有对白`; crowd `不对口型`).

These are one-clause additions per shot; they still count as body edits
beyond the three allowed classes, so they need an explicit go-ahead.

### P1 — Operator meta / unresolved-assumption text inside the model prompt

EP18 units repeatedly tell the model the staging is unverified, e.g.
`上述方位及通行带是待四方位图验证的调度假设` (U02; similar clauses in U01,
U03–U06, EP18-U05 `具体通视角是调度假设`, EP18-U08). The official guides ask
for concrete, resolvable descriptions; the model cannot verify or use a
"pending verification" flag, and it weakens the spatial lock it sits in.
Recommendation (pack-author level): state the方位 as fact and drop the
meta clause, or move the caveat into the staging `.md` files, which the
model never sees.

### P2 — EP18 state blocks repeat and dilute the action

EP18 U02–U06 run 3,600–3,900 characters (EP17: 1,300–2,500). The
`跨集既有状态持续` block appears twice nearly verbatim inside EP18-U05, and
`落点完整状态` restates the handoff at length. Official generation guidance
budgets `detailed_description` at roughly 350–500 English words; far beyond
that, repeated state prose competes with the shot actions. Recommendation:
keep each cross-episode state once (in 接入）, keep 交出 to end-state only.
Author-level edit; do not trim locally without approval.

### P2 — Un-groundable numeric tokens

Coordinates such as `(+1,-1.2)`, crowd scale `两万贵族`, and distances like
`倒飞数十米` are not visually resolvable; the same sentences usually already
carry a visual anchor （栏杆东段 / 看台人群）. Official preference is concrete
composition over abstract numbers. Low risk, author-level tidy-up only.

### P3 — No per-shot timing (accepted project deviation)

Shots are unnumbered `▲` beats inside a fixed 12.0s unit; official base
mode uses `[Shot N]` with timestamps. Prior repo conclusion stands (beat
order already times the unit); only worth an A/B on one spare unit, not a
pack-wide change.

## Not flagged

- The other 14 units still bind full scene fourgrids with the
  `四格参考只用于锁定空间方位` sentence. Per repo rule, crop only when one
  panel matches the camera side; these fight units move around the arena,
  so no single panel locks. Left as-is.
- Negative-phrasing density （不/禁止/不得 ≈ 7–12 per 1k chars) is mostly
  identity/state locks (retention), which the official guides also rely on.
  No change suggested without a controlled A/B.
