# Test2 EP01 G4 production result

## Outcome and provenance

Test2 EP01 U01-U08 were produced and stream-copy assembled into one MP4. U01
came from the verified earlier session `h3-test2-ep01-20260927-103745`; U02-U08
were produced in one manually supervised G4 assignment
`h3-test2-ep01-20260927-164321`. The frozen input manifest SHA-256 is
`2c4f0272f62946c194975e91895fba72f926c4ec62da55abc93fa0ff926f89fb`.
The two motion-latent chains are U01-U04 and U05-U08. U05 is the reviewed
independent-start candidate, not a latent continuation of U04.

Final local output:

`/mnt/d/comfyui-h3-backups/rental-20260924-5090/test2-ep01/final/h3-test2-ep01-20260927-164321/EP01-test2-v1.mp4`

Final Drive output:

`h3drive_h3:comfyui-h3-colab-dedicated/standard-v1/runs/test2-20260925/ep01/h3-test2-ep01-20260927-164321/final/EP01-test2-v1.mp4`

The local and Drive SHA-256 match:
`e23f5c9840b9bd3e4703e8afeb98b5dfeb72007c65e2241bc5a6b9f20e7f3145`.
The MP4 is 60,974,124 bytes. The final receipt is next to the local file and
under the same Drive `final/` directory.

## Runtime, transfer, and cost

| Measure | Observed |
| --- | --- |
| GPU | NVIDIA RTX PRO 6000 Blackwell Server Edition, SM120, 101,974,081,536 VRAM bytes |
| Colab rate | 8.90 CU/hour |
| Manual-session opening balance | 134.80 CU |
| Balance immediately after verified stop | 118.35 CU |
| Balance after delayed billing settled | 117.62 CU (unchanged on a three-minute recheck) |
| Manual-session consumption | 17.18 CU using the settled balance |
| Shutdown | 0 active assignments, 0.00 CU/hour, no sessions |
| Model payload | 41,651,185,023 bytes (38.79 GiB), six verified models |
| Model restore | 630.54 seconds, effective 63.00 MiB/s including part assembly/checks |
| Full restore stage | 642.50 seconds, including source, runner, and historical parent |
| Runtime setup | 28.37 seconds after restore |
| U01 latent recovery | 42,557,400 bytes, downloaded and SHA-256 verified with runtime `rclone v1.60.1-DEV` |
| Final local assembly and Drive delivery | 698.16 seconds after paid shutdown; no additional CU |

The 17.18-CU figure is the observed before/settled-balance delta, not a sum of
estimated phase charges. The first post-stop snapshot suggested only 16.45 CU;
another 0.73 CU posted after shutdown while the usage rate stayed zero. The
630.54-second model-transfer throughput includes
sequential Drive part fetches, local assembly, and checks, so it is not a pure
network-link benchmark. Prior failed G4 assignments and the CPU diagnostic are
not included in this manual-session consumption. The balance from the first
Test2 session (145.22 CU) to the settled balance (117.62 CU) fell by 27.60 CU.

## Per-unit timing and GPU telemetry

The phase wall time includes ComfyUI startup, one prompt, validation,
archiving, and shutdown. Sampler timing and GPU statistics come from each
archived `steps.json` and five-second `nvidia-smi.csv`; utilization is the
arithmetic mean of telemetry samples, not a GPU profiler result.

| Unit | Phase wall (s) | Sampler (s) | Median steps 2-12 (s) | Peak VRAM (MiB) | Mean GPU util | Delivered video |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| U01 | Earlier session; server prompt 568.714 | Earlier session | - | - | - | 15.083333 s / 362 frames |
| U02 | 612.12 | 547 | 46 | 37,303 | 95.4% | 14.166667 s / 340 frames |
| U03 | 582.12 | 524 | 44 | 36,911 | 97.3% | 14.166667 s / 340 frames |
| U04 | 662.09 | 599 | 50 | 38,367 | 98.3% | 14.166667 s / 340 frames |
| U05 | 602.12 | 539 | 45 | 37,415 | 97.2% | 15.083333 s / 362 frames |
| U06 | 662.09 | 595 | 50 | 38,215 | 96.8% | 14.166667 s / 340 frames |
| U07 | 662.12 | 595 | 50 | 38,239 | 96.8% | 14.166667 s / 340 frames |
| U08 | 662.12 | 596 | 50 | 38,247 | 96.8% | 14.166667 s / 340 frames |

U02-U08 phase wall totals 4,444.78 seconds; sampler wall totals 3,995
seconds. The seven successful phase receipts, ComfyUI histories, validation
JSONs, graphs, telemetry, and MP4/latent artifacts are under each unit's Drive
`TEST2_Uxx/` prefix. Local supervision logs and copied metrics are under
`/mnt/d/comfyui-h3-backups/rental-20260924-5090/test2-ep01/sessions/h3-test2-ep01-20260927-164321/`.

## Assembly and quality gates

The eight verified MP4s were concatenated without re-encoding or a second
context trim. The final MP4 has 2,764 H.264 frames at 768x1376 and 24 fps,
115.197673 seconds container duration, 115.166667 seconds video duration,
115.176 seconds AAC duration, and 0.031006 seconds A/V start offset. Full
FFmpeg decode passed. Drive byte size and SHA-256 were checked after upload.

Sampled-frame review found no four-grid rendering or gross identity collapse.
The U01 tail and U02 first frame retain the same rainy platform cast and
geometry. U04 covers the stairs, ring, car-side interaction, and departure;
its final exterior car frame does not independently prove the prompt's exact
seated-in-car handoff state. U05 begins directly in the daylight wedding hall,
matching the intended hard cut and its independent graph. U06 has minor
ring/hand-detail variation in a close-up. The later wedding-hall sampled
frames remain spatially coherent. This is a sampled visual check, not a
frame-by-frame human acceptance of every motion, voice line, or performance.

The five-second full-film contact sheet is local at
`/mnt/d/comfyui-h3-backups/rental-20260924-5090/test2-ep01/final/h3-test2-ep01-20260927-164321/EP01-contact-sheet-5s.jpg`.

## Manual-session control finding

This assignment was supervised stage by stage, not driven by the automatic
host. Pre-install and restore each encountered a CLI WebSocket failure before
the script began; the same assignment remained active and the stage succeeded
after a verified same-session retry. U04 had the same pre-execution failure
and was safely submitted only after confirming no U04 output directory existed.
Before U05, the CLI pruned the local session name after a 404/401 response
while the server still billed one assignment. The existing
`scripts/ops/colab_h3_reattach.py` recovered the original endpoint; U05 was
submitted only after confirming its output directory did not exist. No model
restore was repeated in this successful assignment. Future fixed automation
should separate connection health, server assignment, and prompt receipt
states; it must never treat a local CLI prune as proof that the paid VM ended.
