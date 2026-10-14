# H3 Gate 0: production-safe RTX 5090 window plan

Status: planning only. The rental RTX 5090 is serving production work; do not
restart ComfyUI, scan its large model files, transfer assets, open an observer,
or submit `/prompt` until an exclusive idle window is approved.

## Decision

Most remaining preparation is analysis and needs no GPU. A matched-input
performance screen cannot be completed from the old 5090 logs: the historical
EP04-U02-v16 used a different motion parent and lacks a correlated
server/sampler receipt. Closing that evidence gap needs exactly one new
EP04-U02-v16 inference on the 5090, with the frozen A100 U01 parent and
unchanged graph except the reviewed staging/output paths. No Colab run is
needed for this gate.

## Work and time budget

These are planning ranges, not measured promises. The clock includes rental
time even when no GPU kernels run. Do not combine a production prompt with
the sample: queue/cache contention would invalidate the comparison.

| Phase | Estimated wall | 5090 compute | Production impact / gate |
| --- | ---: | --- | --- |
| Offline manifest, graph, script and evidence review on local D: | 20-40 min, can run now | None | No rental access. Frozen reference audit already replays as `REFERENCE_AUDIT_OK`; archived C2 comparison is `GRAPH_AND_PARENT_ONLY`. |
| Idle-window process/queue/source inventory | 5-10 min | None | Small reads only; require correct `/root/autodl-tmp/ComfyUI` PID and empty queue before going further. Do not stop or replace a process. |
| Six model SHA-256 checks | 10-30 min allowance | None | Reads 41,651,185,023 bytes (38.8 GiB); potentially significant disk I/O. Defer until production is idle. If a model is absent/mismatched, stop without a 45 GiB restore. |
| Stage frozen parent, four references, prompt and small scripts; verify hashes and graph | 5-10 min allowance | None | Parent is 34,602,712 bytes; new non-overwriting path only. Network/disk rate is unmeasured. |
| Output baseline, single observer, bounded telemetry and dry-run admission | 5-10 min | Negligible | Empty unique output prefixes, same observer client ID, no cached sampler and no competing queue item are mandatory. |
| One real 5090 EP04-U02-v16 `/prompt` | 15-25 min reserved | **Yes: one exclusive H3 run** | Old 5090 client observation was 646-656 s (~11 min), but used a different parent and is not a timing guarantee. Stop after one attempt; no automatic retry. |
| History/media/telemetry validation and source-side backup receipt | 10-20 min | None | Instance may still be billable; retain source hashes and small evidence without downloading full media unless needed. |

Allow **50-105 minutes of an exclusive rental window**, including a 15-25
minute inference reserve. The exact cost is `actual rental rate x elapsed
billable time`; no current rate is frozen here. Prefer a separately approved
time and money cap with a stop deadline. If production remains active or the
window is shorter, perform only the offline phase and wait.

## Admission and stop rules

1. Freeze one run ID, the exact manifest/graph/parent hashes, expected model
   and source hashes, output prefixes, approved transfer list, maximum time
   and money, and an operator stop deadline before touching the rental node.
2. At the idle window, inspect the **actual** ComfyUI PID/CWD/start flags,
   GPU/driver/Sage identity, queue and cache state. Do not change the running
   production service. A wrong process, busy queue or unknown source delta
   stops the screen.
3. Hash the six live model files and all prompt/reference inputs. Keep the
   staged parent immutable through node 401 load; hash it before submission
   and after the run. A missing/mismatched asset or any graph delta outside
   the reviewed allowlist stops before POST.
4. Start source-side baselines and one prompt-bound WS observer; require its
   `ready.json` before the one-shot adapter can claim and send `/prompt`.
   Ambiguous transport outcomes consume the claim and require manual
   reconciliation, not a second POST.
5. Capture one run's history, graph, 12-step trace if delivered, environment,
   GPU samples, MP4 and latent checks. Stop and preserve evidence. A single
   sample is a deployment-combination timing screen, not quality acceptance,
   cost parity, a production migration decision, or a variance estimate.

Current disposition: `WAIT_FOR_WINDOW`. No 5090 access, restart, GPU work,
large model hash, asset transfer or real prompt is authorized by this plan.
