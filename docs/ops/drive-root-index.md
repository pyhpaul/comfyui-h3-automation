# ComfyUI H3 Colab Drive index

Canonical documentation and small hash manifests are in the Git repository.
This Drive index separates the tested restore source from new G4 runs.

| Prefix | Role |
| --- | --- |
| `rental-20260924-5090/` | Immutable tested restore snapshot and historical A100/G4 evidence. Do not move or overwrite: archived scripts and receipts reference this exact prefix. |
| `standard-v1/manifests/` | Versioned restore inventory and hashes; does not duplicate large models. |
| `standard-v1/inputs/` | Frozen continuation job/assets packages; SHA-256 recorded in Git manifests. |
| `standard-v1/runtime/g4-sm120/` | G4-specific wheel; see SHA in manifest. |
| `standard-v1/runs/epNN/uNN/<UTC-session>/` | Canonical location for future G4 output and evidence. |
| `standard-v1/runs/epNN/chain/<UTC-session>/` | Shared admission evidence for a serial multi-unit assignment. |

The first successful G4 U02 is historical evidence at
`rental-20260924-5090/g4-u02/h3-g4-u02-20260927-064924/G4_U02/`.
Future runs go to `standard-v1/runs/`; historical evidence is not moved merely
for cosmetic consistency.

Read `standard-v1/README.md` before writing new artifacts. The repository
copy is `docs/ops/drive-layout-v1.md`. Do not place OAuth credentials, rclone
configuration, local rental images, or unverified output in this Drive root.
