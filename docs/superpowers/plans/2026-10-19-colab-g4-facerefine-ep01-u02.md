# Colab G4 FaceRefine EP01 U02 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One supervised Colab G4 run that FaceRefines the EP01 U02 wenwu mp4, publishes before/after + still frames to Drive, stops the assignment, then the agent visually inspects face crops.

**Architecture:** New host mirrors `colab_h3_g4_u02_host.py` (assignment, restore, watchdog, stop) but skips EP04 generation preflight. A remote phase installs FaceRefine, queues one post-pass, validates mp4, publishes. Host pulls evidence and extracts matched-timestamp PNGs for visual review.

**Tech Stack:** Colab CLI, rclone `h3drive_h3`, frozen H3 restore, ComfyUI-H3-FaceRefine, ffmpeg, pytest dry-run gates.

**Spec:** `docs/superpowers/specs/2026-10-19-colab-g4-facerefine-ep01-u02-design.md`

---

## File map

| File | Responsibility |
| --- | --- |
| `scripts/ops/colab_h3_facerefine_g4_host.py` | Dry-run / `--execute-paid` host |
| `scripts/ops/colab_h3_facerefine_phase.py` | Remote: install nodes, queue FaceRefine, publish |
| `scripts/ops/facerefine_extract_frames.py` | Local: ffmpeg before/after frames at shared % |
| `templates/yz_h3_facerefine_test/workflow_api.colab.json` | API graph rebound for Colab model names (filled when known) |
| `tests/test_colab_h3_facerefine_g4_host.py` | Dry-run + receipt gates |

---

### Task 1: Host dry-run skeleton + test

**Files:**
- Create: `scripts/ops/colab_h3_facerefine_g4_host.py`
- Create: `tests/test_colab_h3_facerefine_g4_host.py`

- [ ] **Step 1: Write failing test** — dry-run prints `paid_started=false` and never calls `snapshot` / `colab new`
- [ ] **Step 2: Implement host** — `local_preflight` checks U02 mp4, FaceRefine staging, rclone config, restore scripts; dry-run JSON; `--execute-paid` path stubbed with stages list but wired like G4 U02 (identity → preinstall → restore → setup → facerefine phase)
- [ ] **Step 3: Run pytest** — `tests/test_colab_h3_facerefine_g4_host.py` passes

### Task 2: Frame extract helper + test

**Files:**
- Create: `scripts/ops/facerefine_extract_frames.py`
- Create: `tests/test_facerefine_extract_frames.py`

- [ ] **Step 1: Test** — given two tiny synthetic mp4s (or mocked ffmpeg), writes `t10.png`/`t50.png`/`t80.png` for before and after
- [ ] **Step 2: Implement** — `ffmpeg -ss` at 10%/50%/80% of duration; output dir `frames/before|after/`
- [ ] **Step 3: Pytest pass**

### Task 3: Remote FaceRefine phase

**Files:**
- Create: `scripts/ops/colab_h3_facerefine_phase.py`

- [ ] **Step 1: Install** FaceRefine + NativeAudioLock + YOLO into restored Comfy; pip requirements; ensure Impact-Pack / VideoHelperSuite (clone if missing)
- [ ] **Step 2: Restart/wait Comfy** on 8188; `/object_info` must list `H3FaceTrackCrop`
- [ ] **Step 3: Upload** source mp4 into Comfy `input/`; load API workflow (or build minimal bind from uploaded `workflow_api.colab.json`); set prompt from `prompt_h3.txt`
- [ ] **Step 4: Queue once**; wait history; save `after.mp4`
- [ ] **Step 5: Validate** duration/size vs before; `rclone copy` before/after/prompt/run_meta/logs to Drive prefix; print `FACEREFINE_PHASE_RESULT {...}`
- [ ] **Step 6: Host wires** phase after setup; on success pull evidence **including** mp4s; run frame extract; leave PNGs in `logdir/frames/`

### Task 4: Colab API workflow binding

**Files:**
- Create/update: `templates/yz_h3_facerefine_test/workflow_api.colab.json`

- [ ] **Step 1:** After first Comfy-up in a dry remote probe OR from known restore model filenames in `colab_h3_restore.py`, write API graph with correct UNET/CLIP/VAE names
- [ ] **Step 2:** Document rebinding in phase if filenames drift

### Task 5: Paid run gate + visual confirm

- [ ] **Step 1:** Host dry-run OK; `colab usage` idle; operator confirms CU
- [ ] **Step 2:** Run with `--execute-paid` (only when user explicitly asks in that turn)
- [ ] **Step 3:** After stop, extract frames; **Read** before/after PNGs; report face verdict in chat
- [ ] **Step 4:** Short ops note under `docs/ops/` with run id, CU delta, frame paths

---

## Notes

- Do not reuse `h3_a100_ab_preflight.py` / EP04 U02 graph checks.
- Logdir default: `/mnt/d/comfyui-h3-backups/rental-20260924-5090/g4-facerefine/<session>/` (or repo `.cache/g4-facerefine/` if D: unavailable).
- PATH must include `/home/linux_dev/.local/bin` for `colab`.
