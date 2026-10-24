# Compact visual QC iteration

- [x] Preserve exact source excerpts, offsets and shot/section scope while
      removing repeated source sections from model input. Never merge paraphrases
      or contradictory states. Keep full source and exclusions in local workorders.
- [x] Record local receipt timing: first event, images read, final result, plus
      timeout phase without reasoning text, command arguments, or secrets.
- [x] Test compaction invariants and progress classification, then regress AV/QC.
- [x] Prepare all 16 units locally; compare two full/compact pairs using identical
      image bytes and common prompts, and separately probe the previously silent U.
- [x] Report quality boundaries and measured time; do not infer stable speedups
      from a single pair or retry a silent failure automatically.

No navigation/ASR rerun, media changes, registry writes, mandatory subagent review,
credential changes, MCP transport changes, or Git shipping.

Also removed the fixed-pair scheduling barrier while retaining at most two
in-flight requests and the two-observed-failures circuit. Unit-tested; old live
durations replayed for an estimate, not represented as a new full-batch benchmark.
