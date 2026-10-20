# Colab G4 FaceRefine A/B on EP01 U02

## Problem

EP01 U02 from the 文武双全 TEST batch shows face collapse / soft faces.
Community guidance says H3 face quality tracks **head size in frame**, not
output resolution alone; FaceRefine (detect → crop → H3 redraw → stitch) is the
post-pass meant for that failure mode. The rental GPU is off. Colab G4 has
remaining CU and an existing H3 restore path.

## Goal

Run **one** supervised Colab G4 assignment that:

1. Restores the frozen H3 Comfy runtime from Drive.
2. Installs FaceRefine (+ NativeAudioLock, YOLO detectors; Impact/VHS if missing).
3. Refines the already-rendered EP01 U02 wenwu mp4 (does **not** re-run SelfLift).
4. Publishes before/after artifacts to Drive and stops the assignment.

Operator then judges face quality by eye. No claim that production is fixed.

## Inputs (local, already staged)

| Item | Path |
| --- | --- |
| Source mp4 | `jobs/facerefine_test/source_U02/EP01-U02-mafia2-wenwu_00001-audio.mp4` |
| Prompt | `jobs/facerefine_test/source_U02/prompt_h3.txt` |
| FaceRefine pack | `.cache/facerefine_prep/ComfyUI-H3-FaceRefine/` |
| NativeAudioLock | `.cache/facerefine_prep/ComfyUI-H3-NativeAudioLock/` |
| Detectors | `.cache/facerefine_prep/models/ultralytics/{bbox,segm}/` |
| Example UI graph | `templates/yz_h3_facerefine_test/workflow_ui.auto_select.source.json` |

Feiniu origin (read-only reference):  
`H3_comfyUI_5090/archive/文武双全TEST-黑手党EP01（10.19）/EP01/U02/`

## Approach

Reuse Colab G4 **assignment + restore + watchdog** patterns from
`colab_h3_g4_u02_host.py`, but **do not** reuse the EP04 generation phase /
A100 C1 graph preflight. FaceRefine is a separate post-pass host.

Default graph: FaceRefine **Auto Select** example, rebound to Colab H3
unet/clip/vae names from the frozen restore, source video = uploaded U02 mp4,
prompt = `prompt_h3.txt`. Prefer API-format export prepared offline when
possible; if model filenames on Colab differ, a small remote rebinding step is
allowed once per run.

## Behavior

- Opt-in paid run only: host requires `--execute-paid` (dry-run default).
- Exactly one FaceRefine queue; no automatic retry.
- Paid watchdog deadline (e.g. 3–4 h) so an unattended assignment cannot linger.
- On success or hard failure: stop assignment and verify `Usage rate: 0`.
- Drive publish under a new run id, not under the historical EP04 G4 path.

### Drive layout

```
h3drive_h3:comfyui-h3-colab-dedicated/standard-v1/runs/facerefine/ep01-u02/<run_id>/
  before.mp4          # copy of source
  after.mp4           # FaceRefine output
  prompt_h3.txt
  run_meta.json       # prompt_id, node versions, timings, CU snapshots
  logs/               # host + remote phase logs
```

### Success criteria

- `after.mp4` exists, decodes, duration within ~0.5 s of `before.mp4`, same
  frame size (±32 px tolerance for encoder rounding).
- Assignment stopped; `colab usage` shows no active paid rate.
- **Agent extracts still frames from before/after at the same timestamps
  (at least 3 shared points, e.g. 10% / 50% / 80% of duration), saves them
  under the local evidence dir, and visually inspects face regions** (Read
  tool on the PNGs) before declaring the run useful. Publish those PNGs to
  Drive `frames/` as well. Do not claim success on file presence alone.

### Failure criteria (do not spend a second paid run automatically)

- Restore or node install fails.
- FaceRefine queue errors / OOM.
- Receipt / publish incomplete after stop — investigate offline; no auto-rerun.

## Non-goals

- Re-running 文武双全 / SelfLift generation on Colab.
- Writing FaceRefine into production `yz_h3_ep_unit` or Feiniu production batches.
- Refining U01 in the same assignment.
- Automatic perceptual “face quality score”.
- Replacing the rental-GPU FaceRefine prep already under
  `templates/yz_h3_facerefine_test/` (that path remains for when the pod returns).

## Components

1. **`scripts/ops/colab_h3_facerefine_g4_host.py`** — supervised host: dry-run /
   `--execute-paid`, upload assets, stages, stop+verify. Patterned on
   `colab_h3_g4_u02_host.py` but FaceRefine-only.
2. **`scripts/ops/colab_h3_facerefine_phase.py`** (remote) — after restore:
   install custom nodes + detectors, ensure Impact/VHS, bind/queue FaceRefine,
   validate mp4, write receipt, rclone publish.
3. **Staged workflow** — API graph under `templates/yz_h3_facerefine_test/` once
   rebound for Colab model names; keep UI source as fallback.
4. **Tests** — host dry-run (`paid_started=false`), path/marker checks; no paid
   Colab in CI.

## Cost envelope (estimate, not invoice)

Historical G4 rate ~8.9 CU/h. Prior full U02 gen used ~3 CU including ~10 min
restore. This run: restore + one FaceRefine pass → rough **3–5 CU**. Exact
spend from before/after `colab usage` snapshots in `run_meta.json`.

## Gate before `--execute-paid`

- [ ] `colab` CLI on PATH; usage shows spare CU and zero active assignments
- [ ] rclone `h3drive_h3:` works; frozen restore remote reachable
      (`rclone config reconnect h3drive_h3: --config ~/.config/rclone-h3/rclone.conf`)
- [ ] Local U02 mp4 + FaceRefine staging present
- [ ] Host dry-run exits 0 with `paid_started=false`
- [ ] Operator explicitly passes `--execute-paid`
- [ ] After pull: agent extracts and visually Reads before/after frame PNGs
