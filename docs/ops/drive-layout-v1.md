# H3 Drive layout v1

Drive root: `h3drive_h3:comfyui-h3-colab-dedicated`.

## Decision

`rental-20260924-5090/` is the immutable, already-tested restore snapshot
and historical experiment archive. Do not rename or move it: existing Colab
restore scripts, receipts, and published evidence refer to that exact path.
Do not duplicate its 38.79 GiB model set merely to obtain a tidier tree.

New G4 work uses `standard-v1/`:

```text
standard-v1/
  README.md
  manifests/
    restore-rental-20260924-v1.json
    drive-chain-ep04-u03-u05-v1.json
  inputs/
    ep04/manual-v16/ep04-manual-v16-u03-u05.tar
  runtime/
    g4-sm120/
      sageattention-2.2.0-cp313-cp313-linux_x86_64.whl
  runs/
    epNN/
      uNN/
        h3-g4-uNN-YYYYMMDD-HHMMSS/
          preflight.json
          G4_U02/
            phase.json
            run/validation.json
            run/submitted_graph.json
            run/downloads/...mp4
            run/downloads/...safetensors
            comfyUI.log
            nvidia-smi.csv
      chain/<session>/
        preflight.json
        chain-inputs.json
```

Use lowercase `epNN/uNN` path components, a UTC timestamped session ID, and
one directory per assignment. Never overwrite an existing run. Upload the
verified `phase.json` receipt last. Preserve the graph, history, validation,
telemetry, logs, MP4 and AV latent together under the run directory. A failed
or ambiguous run keeps its evidence and is marked failed; it is not silently
replaced by a second prompt.

The successful first G4 U02 remains at its original historical path:
`rental-20260924-5090/g4-u02/h3-g4-u02-20260927-064924/G4_U02/`.
Its direct Drive file ID and D: backup are already recorded in
`2026-09-27-h3-colab-g4-u02-result.md`. Do not copy or move it solely to make
the layout look uniform.

## Placement rules

| Item | Canonical home |
| --- | --- |
| Code, setup scripts, tests, runbooks, hash manifests | Git repository |
| Frozen source/model/parent restore snapshot | Existing `rental-20260924-5090/` Drive prefix and D: backup |
| GPU-specific binary wheel | `standard-v1/runtime/<gpu-arch>/` in Drive, D: backup; SHA in Git |
| Frozen job/assets continuation packages | `standard-v1/inputs/<episode>/<pack>/` in Drive and D: backup; hash manifest in Git |
| Future generation outputs and evidence | `standard-v1/runs/<episode>/<unit>/<session>/` in Drive |
| OAuth tokens, `rclone.conf`, API credentials | Local secret store only; never Git or Drive |
| Original large rental image/filesystem backup | D: only; do not upload unused 45+ GiB archives to Drive |

The restore snapshot is versioned by its manifest, not by whichever GPU is
currently selected. Keep current experiments and production outputs separate
from the immutable restore source. If a model or source byte changes, create a
new restore manifest and prefix; do not overwrite the v1 snapshot.

## Verification and future writes

1. Verify `colab usage` has zero active assignments before Drive maintenance.
2. Before a paid run, check the restore manifest, wheel SHA, available Drive
   space, intended output prefix, and that the session directory does not
   already exist.
3. After a run, verify output count, media/latent properties, graph, input
   hashes and Drive `rclone check`; publish the terminal receipt last.
4. Stop the Colab assignment, confirm `Usage rate: 0.00/hr` and no sessions,
   then copy only small evidence to D:. Keep MP4/latent on Drive unless needed
   for review or an independent hash check.

The Drive index is a navigation and storage contract. It does not claim the
historical A100 trials or the original G4 run were retroactively moved or
revalidated. On 2026-09-27 the Drive root held 297 objects and 39.848 GiB.
