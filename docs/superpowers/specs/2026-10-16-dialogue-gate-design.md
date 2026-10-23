# Dialogue gate before motion_latent handoff

## Problem

Prompt hard-locks reduce ad-lib speech but cannot stop H3 sampling noise. Dirty
audio on a finished unit is stored in the AV latent; the next unit regenerates
the parent’s last second and can inherit garbled phonemes.

## Goal

Before printing `HANDOFF` / setting `parent_latent` for the next unit, transcribe
the finished mp4 and compare it to `（）` English lines in `prompt_source.txt`.
Fail the unit (retry, then abort the batch) instead of poisoning the chain.

## Behavior

- Opt-in via `--dialogue-gate` (also `H3_DIALOGUE_GATE=1`).
- `--dialogue-gate-retries N` (default 2): re-queue the same unit on fail; do not
  advance `parent_latent` until a take passes.
- Silent units (`本条没有任何对白` in source): any intelligible speech → fail.
- Spoken units: missing expected lines or unmatched / low-match segments
  (especially the last segment) → fail. Number forms (`38,000` vs
  `thirty-eight thousand`) normalize as match.
- On pass: existing handoff + background Feiniu archive unchanged.
- On final fail: `DIALOGUE_GATE_FAIL`, exit 2, join archive threads already
  started for prior units.

## Non-goals

- Replacing pack `audit_pack_prompts.py` (still pre-queue wiring only).
- Requiring faster-whisper in the default install: gate errors clearly if ASR
  backend missing when enabled.
- Auto-breaking the next unit to `independent` (operator re-runs from last
  clean latent).

## Components

1. `comfy_orch.dialogue_gate` — extract expected lines, score transcript (pure).
2. ASR adapter — `transcribe_mp4(path) -> {heard, segments}`; faster-whisper when
   importable.
3. `run_ep_units_profiled.py` — download mp4 before handoff when gate on; retry
   loop per unit.
