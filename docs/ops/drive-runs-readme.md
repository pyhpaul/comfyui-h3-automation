# Standard H3 run archive

Future runs use `epNN/uNN/<UTC-session>/`. Every session name is unique and
immutable after its verified terminal receipt is published. Keep the MP4,
paired AV latent, submitted graph, history, validation, telemetry, logs and
receipt in the same session tree. A failed run keeps its diagnostic artifacts
and must not be overwritten by a retry.

The restore snapshot remains under `../../rental-20260924-5090/`; do not copy
models into each run. Refer to `../manifests/restore-rental-20260924-v1.json`
for the frozen input hashes and `../README.md` for the full layout contract.
