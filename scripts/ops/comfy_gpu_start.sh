#!/usr/bin/env bash
# Run ON the GPU rental host.
# Canonical H3 ComfyUI start for orchestration (vm122:8190 → 127.0.0.1:8188).
# Prefer this over platform /root/restart.sh (which listens 0.0.0.0 with different flags).
set -euo pipefail

COMFY_ROOT="${COMFY_ROOT:-/root/autodl-tmp/ComfyUI}"
LOG="${COMFY_H3_LOG:-$COMFY_ROOT/comfyUI-h3.log}"

cd "$COMFY_ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate

unset PYTORCH_CUDA_ALLOC_CONF
unset PYTORCH_ALLOC_CONF
export CUDA_VISIBLE_DEVICES=0
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

case "${H3_DISABLE_SMART_MEMORY:-1}" in
  1) memory_flag=(--disable-smart-memory) ;;
  0) memory_flag=() ;;
  *) echo "H3_DISABLE_SMART_MEMORY must be 0 or 1" >&2; exit 2 ;;
esac

exec python main.py \
  --listen 127.0.0.1 \
  --port 8188 \
  --cuda-device 0 \
  --lowvram \
  --reserve-vram 4 \
  "${memory_flag[@]}" \
  --force-fp16 \
  --disable-cuda-graphs \
  --enable-manager \
  >>"$LOG" 2>&1
