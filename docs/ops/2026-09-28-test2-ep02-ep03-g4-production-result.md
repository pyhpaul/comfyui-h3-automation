# Test2 EP02/EP03 G4 production and cost record

## Outcome and acceptance boundary

The accepted Test2 EP02 (7 units) and EP03 (8 units) jobs were each submitted
once to ComfyUI on the same Colab G4 assignment
`h3-test2-ep23-20260928-090407`. All 15 attempts ended with `success`,
`archive_state=verified`, a ComfyUI history success, one MP4 and one finite AV
latent. Both episode MP4s were stream-copy assembled, fully decoded and
uploaded to Drive. This is **technical delivery**, not complete visual or
dialogue acceptance.

EP03 U07 **failed its explicit visual gate**: its first frame shows Sean,
Grant, Claire and Riva standing around the wedding table, rather than
continuing U06's last state in which a goon restrains Helen on the floor.
Later sampled frames return to the restraint. It does not establish the
specified one-second daytime tail followed by a night cut. U08 was generated
from U07's verified latent to finish the technical episode, so EP03's final
MP4 is a review candidate and must not be marked quality-approved. Re-running
the unchanged U07 graph would reuse its fixed noise seed and is not an
evidence-based correction.

The archived U07 graph **did** load
`h3_context/ep03_u06_00006.safetensors` at clip index 6, with the expected
MotionContext and Trim nodes and all nine image inputs. This is a model/output
continuity failure, not evidence that the runtime omitted the parent latent.
Two contributing risks remain hypotheses: U07's nine still-image slots omit
Helen and goon B while emphasizing the wedding group; and the source prompt
asks to keep 24 old-tail frames while the established MotionContextTrim graph
removes its 22-frame context overlap from the delivered MP4. A corrective
candidate needs explicit reference/transition review, not a blind same-seed
retry.
An additional one-frame-per-second sheet of the delivered U07 MP4 shows
the wedding-table group through roughly seconds 0-9 and the Helen restraint
only in the final roughly 4 seconds. The defect is therefore sustained shot
order/timing, not a single bad opening frame. That sheet is local at
`/mnt/d/comfyui-h3-backups/rental-20260924-5090/test2-ep02-ep03/sessions/h3-test2-ep23-20260928-090407/EP03_U07-contact-sheet-1s.jpg`.

| Episode | Local final | Drive final | Frames / video duration | Bytes | SHA-256 |
| --- | --- | --- | --- | ---: | --- |
| EP02 | `/mnt/d/comfyui-h3-backups/rental-20260924-5090/test2-ep02-ep03/final/h3-test2-ep23-20260928-090407/EP02/EP02-test2-v2.mp4` | `h3drive_h3:comfyui-h3-colab-dedicated/standard-v1/runs/test2-20260925/ep02-ep03/h3-test2-ep23-20260928-090407/final/EP02-test2-v2.mp4` | 2468 / 102.833333 s | 39835782 | `63d29ffa42841e646e49687207e4a6f00f4cb57bb7751bc258fe7d64e2d9c8b9` |
| EP03 | `/mnt/d/comfyui-h3-backups/rental-20260924-5090/test2-ep02-ep03/final/h3-test2-ep23-20260928-090407/EP03/EP03-test2-v1.mp4` | `h3drive_h3:comfyui-h3-colab-dedicated/standard-v1/runs/test2-20260925/ep02-ep03/h3-test2-ep23-20260928-090407/final/EP03-test2-v1.mp4` | 2742 / 114.250000 s | 53896586 | `7a693bc6f6a31990e5d159402b680e2a95b44556e85207bcc618f4850523fd16` |

The finalizer checked every unit's identity-bound Drive receipt, parent path,
MP4 size and SHA-256, then downloaded only the 15 MP4s. Assembly did not
re-encode or trim child units a second time. Full FFmpeg decode, aggregate
frame count, A/V duration and Drive size/hash checks passed. Episode final
receipts are in each local final directory and the Drive `final/` directory.

## Frozen inputs and runtime

- Source ZIP SHA-256:
  `9927f713bebff146ff10f51e7311df8e32a55e1eb3ae422a2ba832c1c4029ef0`.
  Accepted input manifest SHA-256:
  `54f2a1e0e9b256d189e4a17ed99de627d8cdfb9d35cb309b2544f813f33d029a`.
- The selected 15-job archive is 200146604 bytes with SHA-256
  `d73ff9de1137601d3625a90cdb2842cbfbb32e29208a963700d1611434e083ab`.
  It was uploaded to Drive once before the paid assignment. The runtime
  downloaded and SHA-256-checked this same archive, then installed the
  separately verified API-nine overlay (SHA-256
  `4c774aa0f6299ad2142712bf1b47845ea0f4ef567a890ad41f6603beb80b4a63`).
  No 191-MiB archive re-upload and no second 38.79-GiB model restore occurred.
- EP02 independent starts were U01/U02/U04/U06; EP03 U01 was independent.
  Other units loaded only the immediately preceding verified latent. Runtime
  no-queue validation checked all 15 jobs, image binding (3-9 refs), one-pass
  12-step graph, active H3 nodes, and GPU identity before U01 submission.
- Assigned GPU: NVIDIA RTX PRO 6000 Blackwell Server Edition, SM120,
  101974081536 VRAM bytes (97887 MiB reported by `nvidia-smi`), driver
  580.82.07. The ComfyUI venv used Python 3.13, PyTorch
  `2.14.0+cu130`, and the verified SageAttention 2.2.0 cp313 SM120 wheel.
  Colab's base Python initially reported PyTorch `2.11.0+cu128`; that was
  not the ComfyUI venv used for generation. Runtime apt rclone was
  `v1.60.1-DEV`; local CLI was `0.7.2`.

## Transfer, runtime and Compute Units

| Measure | Observed |
| --- | ---: |
| Assignment created / terminated (UTC, CLI history) | 2026-09-28 09:04:27.947 / 12:39:03.132 |
| Paid assignment elapsed | 12875.185 s (3 h 34 min 35.185 s) |
| Usage rate | 8.90 CU/hour |
| Balance before / immediately after stop / settled | 117.62 / 86.48 / 85.73 CU |
| Settled consumption | **31.89 CU** |
| Final state | 0 active assignments; 0.00 CU/hour; no active sessions |
| Frozen model payload | 41651185023 bytes (38.79 GiB), six models |
| Model restore | 697.83 s; effective 56.92 MiB/s including part download, assembly and checks |
| Complete restore phase | 712.63 s, including source, runner and historical parent |
| G4 transport / runtime setup | 10.67 s internally for transport; 26.78 s setup to `comfy_ready` |
| Accepted jobs transfer/install stage | 13.78 s CLI wall for 191 MiB; effective 13.85 MiB/s including hashing/extraction |
| All 15 unit phase walls | 10441.77 s; EP02 4424.79 s; EP03 6016.98 s |
| All 15 ComfyUI server prompt walls | 10180.839 s |
| All 15 sampler walls | 9346 s |
| Off-GPU final assembly/Drive delivery | EP02 427.83 s; EP03 481.00 s; no additional CU |

The 31.89 CU is the observed starting-to-settled balance delta, not a sum
of rounded stage estimates. The first stop reading understated it by 0.75
CU; subsequent `colab usage` checks were stable at 85.73 CU with zero rate
and zero assignments. At 8.90 CU/hour, the 15 unit phases account for about
25.81 CU of time-equivalent usage; the remaining roughly 6.08 CU covers
restore, setup, manual review/reconciliation gaps and shutdown. These are
planning allocations, not per-episode invoice lines. The model throughput is
not a pure network benchmark. The accepted archive's prior local-to-Drive
upload took about 35 s (about 5.45 MiB/s), before this paid session.

The actual source/runner/model restore was reused within one assignment even
after three CLI 404/401 local-session prunes. Each prune was reconciled
against the still-active server assignment, reattached to the same endpoint,
and checked for a missing next-unit output before retrying. U04 also hit a
prequeue environment-variable carryover: Colab's notebook kernel retained
U03's parent latent on the new independent start. The guard rejected U04
before creating an attempt directory or queueing; explicit empty parent
variables allowed same-session retry. `colab exec` returned exit code zero
for that notebook traceback, so exit code alone is not a success signal.

## Per-unit GPU and generation measurements

`Phase` includes ComfyUI start, prompt, validation, archiving and stop.
`Sampler` and median step are from archived `steps.json`; VRAM and mean GPU
utilization are from five-second `nvidia-smi.csv` samples. Mean utilization
is an arithmetic sample mean, not a profiler result. Unit MP4 sizes are
rounded MiB; exact bytes and hashes are in the final receipts.

| Unit | Phase s | Server s | Sampler s | Median step 2-12 s | Peak VRAM MiB | Mean GPU util | MP4 MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EP02 U01 | 702.13 | 682.617 | 622 | 52 | 39191 | 97.0% | 6.23 |
| EP02 U02 | 562.07 | 543.622 | 498 | 42 | 36479 | 96.1% | 6.26 |
| EP02 U03 | 612.10 | 599.195 | 555 | 47 | 37287 | 97.3% | 4.16 |
| EP02 U04 | 532.11 | 516.987 | 473 | 40 | 35751 | 95.6% | 5.28 |
| EP02 U05 | 592.14 | 570.924 | 530 | 45 | 36903 | 96.0% | 5.42 |
| EP02 U06 | 692.12 | 679.565 | 620 | 52 | 39103 | 98.3% | 5.68 |
| EP02 U07 | 732.12 | 711.908 | 656 | 55 | 39455 | 96.2% | 5.09 |
| EP03 U01 | 702.12 | 684.512 | 623 | 52 | 39135 | 97.6% | 5.77 |
| EP03 U02 | 732.13 | 711.230 | 655 | 55 | 39327 | 97.2% | 6.66 |
| EP03 U03 | 752.11 | 739.854 | 680 | 57 | 39975 | 98.6% | 5.87 |
| EP03 U04 | 762.12 | 744.590 | 683 | 57 | 39975 | 97.3% | 6.58 |
| EP03 U05 | 762.12 | 745.114 | 685 | 57 | 39999 | 97.6% | 7.43 |
| EP03 U06 | 762.11 | 746.428 | 686 | 58 | 40007 | 97.6% | 6.97 |
| EP03 U07 | 772.12 | 752.537 | 690 | 58 | 40135 | 97.5% | 5.99 |
| EP03 U08 | 772.15 | 751.756 | 690 | 58 | 40103 | 96.8% | 6.31 |

Across the units, the mean phase was 696.12 s, mean sampled GPU
utilization 97.1%, and peak observed VRAM 40135 MiB. This run was
compute-active while sampling, not limited by the 95-GiB VRAM capacity.

## Quality evidence and next gate

EP02 U02/U04/U06 sampled frames start in the motel, rental room and wedding
hall respectively, with no old-scene first frame or four-grid render seen.
EP03 U04's hospital reference appeared inside the phone on sampled frames,
not as a full-scene replacement. EP03 U05/U06 sampled frames showed the
separate goon/Helen/Grant/Briggs action group, but do not establish every
actor's identity and motion through the complete clips. EP03 U07's wrong
first frame is a concrete continuity failure; U08's sampled first frame
returns to the restrained-Helen state, but does not repair U07.

A second offline audit generated one-frame-per-second contact sheets for all
15 unit MP4s under
`/mnt/d/comfyui-h3-backups/rental-20260924-5090/test2-ep02-ep03/final/h3-test2-ep23-20260928-090407/quality-audit/`.
EP02 U01-U07 sampled shots showed their expected wedding, motel and rental
room scene progression without a newly observed hard scene-reset defect.
EP03 U01-U06 showed the expected wedding-floor discovery, phone confrontation
and restraint progression. EP03 U07's first roughly nine seconds instead
returned to the standing wedding-table group before the restraint appeared;
this remains the decisive visual failure. EP03 U08 alternated among Briggs,
Helen's restraint and the wedding-table guest, broadly matching its scripted
shot list, but its continuity cannot be accepted while U07's preceding
segment is wrong. These sheets are sparse visual sampling only: they do not
verify every frame, dialogue intelligibility, lip sync or subjective quality.

Both assembled MP4s contain stereo AAC audio at 32 kHz, with audio duration
within 0.01 s of the video duration (EP02 102.842656 vs 102.833333 s; EP03
114.259344 vs 114.250000 s). An offline `silencedetect=noise=-40dB:d=1`
scan found intermittent quiet passages, with the longest detected intervals
3.326 s in EP02 and 3.802 s in EP03; neither file is globally silent. This
is stream-presence/level evidence only, not verification of the required
English lines, speaker identity, intelligibility or audio-video sync.

The offline evidence mirror is under
`/mnt/d/comfyui-h3-backups/rental-20260924-5090/test2-ep02-ep03/sessions/h3-test2-ep23-20260928-090407/evidence/`.
It contains 15 phase receipts, validation reports, submitted graphs,
ComfyUI logs, step timings, GPU telemetry and review frames (5.170 MiB
excluding MP4/latent). The raw MP4s and latents remain in Drive under each
`EPxx_Uxx/a01/` prefix. CLI history is local at `colab-session.jsonl` in
the same session directory. The final outputs and receipts are complete,
but EP03 U07 needs a separately reviewed corrective candidate before EP03
can be called visual-quality accepted; full human viewing of both films
remains open.

## Proposed correction gate (not yet run)

Prepare a new, separately versioned EP03 U07 candidate from the accepted
source; do not alter the frozen 15-job archive or overwrite U07/U08 receipts.
The narrow hypothesis is to replace low-priority veil/glass still-image slots
with Helen and the restraining goon, and to put the U06 floor-restraint tail
and the post-overlap night transition ahead of the wedding-table reactions
in the U07 prompt. Preserve the named characters, required dialogue, phone
screen, seat card and final state in text. Before any paid submission, check
all nine image bindings, the submitted graph's actual parent latent and trim,
the prompt's timing semantics, and expected U07-to-U08 handoff. This is a
candidate to test, not a claimed root-cause fix or quality approval.

If a paid correction is authorized, restore once on one G4 assignment, run
U07 alone, inspect its first frame and one-frame-per-second progression, then
run U08 from the corrected verified latent only if U07 passes. Keep the same
assignment through recoverable CLI/script failures after reconciling remote
receipts; do not blindly resubmit an uncertain prompt. Reassemble EP03 under
a new output version, verify full decode, Drive hash and settled CU/stop state.
The previous U07+U08 phases totaled 1544.27 s (25.74 min); this is measured
generation time only, not a new-session time or CU promise. A new session
would also pay for the approximately 12-minute model restore and review time.
