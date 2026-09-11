# EP → H3 R2V Prompt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a rule-based EP→H3 six-section prompt converter, a U01 gold fixture, wire it into `ep_pack`, and re-run EP03-U01 for quality comparison.

**Architecture:** Pure function `build_h3_r2v_prompt(ep_text, slots)` in `h3_prompt.py`; `ep_pack.build_unit_job` calls it and writes `prompt` + source artifacts. Gold prompt stored under `tests/fixtures/` for structural assertions.

**Tech Stack:** Python 3, pytest, existing `comfy_orch` / Comfy API client

---

### Task 1: Failing tests for H3 prompt builder

**Files:**
- Create: `src/comfy_orch/h3_prompt.py` (stub later)
- Create: `tests/test_h3_prompt.py`
- Create: `tests/fixtures/ep03_u01_h3_gold.txt` (after Task 2; initially assert structure only)

- [ ] **Step 1: Write failing tests** for: six section headers present; `<Picture 1>` storyboard language; identity Subjects from pictures 2+; `<Video 1>` motion-only; `non_diegetic_music: N/A`; no `assets/` path strings; strips upload-order block
- [ ] **Step 2: Run pytest** — expect import/fail
- [ ] **Step 3: Implement minimal `h3_prompt.py`**
- [ ] **Step 4: Tests green**

### Task 2: U01 gold prompt + structural compare

**Files:**
- Create: `tests/fixtures/ep03_u01_h3_gold.txt`
- Modify: `tests/test_h3_prompt.py`

- [ ] Hand-write gold from EP03 U01 + YZ sample style
- [ ] Assert converter shares required labels/sections with gold (not full string equality)

### Task 3: Wire into `ep_pack`

**Files:**
- Modify: `src/comfy_orch/ep_pack.py`
- Modify: `tests/test_ep_pack.py`

- [ ] `fields.prompt` = H3 text; write `prompt_source.txt` + `prompt_h3.txt`
- [ ] Update pack tests

### Task 4: Rebuild U01, submit, pull, compare

**Files:**
- Ops only under `jobs/` / `outputs/` / Downloads

- [ ] Rebuild EP03-U01 job
- [ ] Export/bind + queue on `COMFY_BASE_URL`
- [ ] Monitor + pull to `outputs/` and `C:\Users\lxy\Downloads\EP03-U01-h3-prompt-v2\`
- [ ] Note prior clip path for side-by-side
