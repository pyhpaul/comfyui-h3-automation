# Dialogue Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Block motion_latent handoff when rendered speech does not match pack `（）` lines.

**Architecture:** Pure `dialogue_gate` scoring in `comfy_orch`; optional faster-whisper ASR; profiled runner downloads mp4 and retries before `HANDOFF` when `--dialogue-gate` is set.

**Tech Stack:** Python 3.11, pytest, optional `faster-whisper`, ffmpeg CLI for wav extract.

---

### Task 1: Expected lines + score (pure)

- [ ] Write `tests/test_dialogue_gate.py` for extract + score cases (silent, extras, number forms, tail junk)
- [ ] Run pytest — fail (module missing)
- [ ] Implement `src/comfy_orch/dialogue_gate.py`
- [ ] Run pytest — pass

### Task 2: ASR adapter (optional import)

- [ ] Tests with fake transcribe callable; real import skipped if missing
- [ ] Implement `transcribe_mp4` wrapper in same module

### Task 3: Runner gate + retries

- [ ] Extend `tests/test_profiled_archive_handoff.py` or add `test_dialogue_gate_runner.py` for retry-clears-parent / fail-blocks-handoff helpers
- [ ] Wire `--dialogue-gate`, `--dialogue-gate-retries` in `scripts/run_ep_units_profiled.py`
- [ ] Update pack-audit skill / queue-run note: gate is post-render

### Task 4: Verify

- [ ] `pytest tests/test_dialogue_gate.py tests/test_profiled_archive_handoff.py -q`
