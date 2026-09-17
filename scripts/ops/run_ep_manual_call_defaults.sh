#!/usr/bin/env bash
# Run EP units with locked H3 manual-call defaults:
#   continuity=motion_latent, no second-pass, gpu-profile=auto
#
# Usage:
#   bash scripts/ops/run_ep_manual_call_defaults.sh \
#     --job-glob 'EP04-H3-manual-v16-{unit}' \
#     --units U01 U02 U03 \
#     --download-dir /mnt/c/Users/lxy/Downloads/EP04-manual-v16-latent-mc \
#     [--batch-log runs/ep04_manual_v16.json]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "${ROOT}/.worktrees/feat-orch/.venv/bin/activate" 2>/dev/null \
  || source "${ROOT}/.venv/bin/activate"

if [[ -f "${ROOT}/scripts/ops/h3_manual_call_run_defaults.env" ]]; then
  # shellcheck disable=SC1091
  source "${ROOT}/scripts/ops/h3_manual_call_run_defaults.env"
elif [[ -f "${ROOT}/scripts/ops/h3_manual_call_run_defaults.env.example" ]]; then
  # shellcheck disable=SC1091
  source "${ROOT}/scripts/ops/h3_manual_call_run_defaults.env.example"
fi

export COMFY_BASE_URL="${COMFY_BASE_URL:-http://192.168.5.122:8190}"
GPU_PROFILE="${COMFY_GPU_PROFILE:-auto}"
CONTINUITY="${H3_MANUAL_CONTINUITY:-motion_latent}"

JOB_GLOB=""
UNITS=()
DOWNLOAD_DIR=""
BATCH_LOG=""
EXTRA=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --job-glob) JOB_GLOB="$2"; shift 2 ;;
    --units)
      shift
      while [[ $# -gt 0 && "$1" != --* ]]; do UNITS+=("$1"); shift; done
      ;;
    --download-dir) DOWNLOAD_DIR="$2"; shift 2 ;;
    --batch-log) BATCH_LOG="$2"; shift 2 ;;
    *) EXTRA+=("$1"); shift ;;
  esac
done

if [[ -z "$JOB_GLOB" || ${#UNITS[@]} -eq 0 || -z "$DOWNLOAD_DIR" ]]; then
  echo "need --job-glob --units --download-dir" >&2
  exit 1
fi

ARGS=(
  scripts/run_ep_units_profiled.py
  --units "${UNITS[@]}"
  --continuity "$CONTINUITY"
  --gpu-profile "$GPU_PROFILE"
  --job-glob "$JOB_GLOB"
  --download-dir "$DOWNLOAD_DIR"
)
if [[ -n "$BATCH_LOG" ]]; then
  ARGS+=(--batch-log "$BATCH_LOG")
fi
# intentionally no --second-pass
ARGS+=("${EXTRA[@]}")

echo "defaults: continuity=$CONTINUITY second_pass=0 gpu_profile=$GPU_PROFILE base=$COMFY_BASE_URL"
exec python -u "${ARGS[@]}"
