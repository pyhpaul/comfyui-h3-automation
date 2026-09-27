# G4 EP04 U03-U05 continuation gate

## Frozen scope

- One Colab G4 assignment, serial `U03 -> U04 -> U05`; one prompt per unit, no retry on uncertain state.
- Reuse the successful G4 U02 raw AV latent as U03 parent; U04 and U05 consume the immediately preceding unit's verified raw latent.
- Keep `motion_latent`, one pass, 12 sampler steps, SageAttention SM120, the frozen EP04 manual-v16 jobs and all media validation. No resolution, frame-rate, duration, prompt or reference-image reduction.
- The original restore snapshot contains only U02 jobs. The additional U03-U05 job/assets tar is frozen separately by `drive-chain-ep04-u03-u05-v1.json`; it is 21,637,120 bytes, not another model upload.
- Each unit is backed up and receipt-verified on Drive before the next unit is submitted. ComfyUI restarts between units in this first chain gate; the experiment amortizes the 41.65 GB restore, not yet ComfyUI process startup or model loading.

## Storage and identity

- Frozen package: `standard-v1/inputs/ep04/manual-v16/ep04-manual-v16-u03-u05.tar`.
- Shared preflight: `standard-v1/runs/ep04/chain/<session>/`.
- Per-unit outputs: `standard-v1/runs/ep04/u03/<session>/G4_U03/`, then `u04` and `u05` in the same pattern.
- U02 parent remains in the historical `rental-20260924-5090/g4-u02/...` directory. Its Drive SHA-256 equals the U02 validation receipt: `fe7bba15b43bcaee71ddc2b0d6e22681bae841842e351a9eccbdf9f543fcb992`.
- The package SHA-256 is `a5c7f63fc53a8aaefa7f72f14e7177be35f6de74f13ebe16e30ff8d69c1ff687`; the Drive object reports the same hash.

## Execution controls

1. Review PR #4 first: it contains the source-controlled restore/setup baseline used here. This follow-on chain code is not yet a paid-run-proven deployment.
2. Run `python3 scripts/ops/colab_h3_g4_chain_host.py` without `--execute-paid`. It verifies local wheel/archive, Drive size and SHA-256, restore archive, and reports `paid_started=false`.
3. Confirm the exact session inputs and outputs, current `colab usage`/`colab sessions`, and the available Drive capacity. The proposed budget is 20 CU with an independent two-hour watchdog. At the prior observed 8.90 CU/hour, the two-hour ceiling models near 17.8 CU, not a settled charge or a contractual rate. If the assigned rate multiplied by the watchdog window exceeds 20 CU, the host stops before uploading or running prompts.
4. Only after authorization, use `python3 scripts/ops/colab_h3_g4_chain_host.py --execute-paid --safety-hours 2 --max-cu 20`. The host performs identity, Torch preinstall, immutable restore, setup, base asset preflight, U03-U05 input admission, then the serial units. Each unit has a terminal receipt, graph/latent/media checks, telemetry, timing and a Drive archive. The host stops the assignment in `finally` and verifies no active billing.
5. Stop immediately if identity, hash, model restore, parent latent, graph contract, prompt history, 12-step telemetry, output validation, Drive verification or receipt identity fails. Do not submit the next unit and do not blindly retry the same one. Reconcile Drive receipts before any separate recovery plan.

## Validation status

The package, Drive SHA, parent Drive SHA, manifest, and host no-pay dry-run were checked on 2026-09-27. An offline extraction of the frozen runner and U03-U05 job tar constructed all three runtime graphs; each passed the frozen SageAttention, 12-step, output and parent-latent graph gate. The new Colab chain path, new source-controlled restore path, sequential continuity and two-hour timing have **not** been tested on a paid G4 assignment. Dry-run readiness is not evidence of U03-U05 successful output.
