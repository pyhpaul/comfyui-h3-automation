#!/usr/bin/env bash
# Restart Comfy tunnel on vm122. Run ON vm122 (or: ssh vm122 'bash -s' < this file).
# Prerequisites: /tmp/comfy-fwd-venv with paramiko; password file; host/port env or patched script.
set -euo pipefail

PASSFILE="${COMFY_GPU_SSH_PASSFILE:-/tmp/.comfy_gpu_ssh_pass}"
LISTEN="${COMFY_TUNNEL_LISTEN:-8190}"
LOG="${COMFY_TUNNEL_LOG:-/tmp/comfy_ssh_forward.log}"
VENV_PY="${COMFY_FWD_PYTHON:-/tmp/comfy-fwd-venv/bin/python}"
SCRIPT="${COMFY_FWD_SCRIPT:-/tmp/comfy_ssh_forward.py}"

if [[ ! -f "$PASSFILE" ]]; then
  echo "missing password file: $PASSFILE (chmod 600)" >&2
  exit 1
fi
if [[ ! -x "$VENV_PY" && ! -f "$VENV_PY" ]]; then
  echo "missing venv python: $VENV_PY" >&2
  exit 1
fi
if [[ ! -f "$SCRIPT" ]]; then
  echo "missing forwarder script: $SCRIPT" >&2
  echo "copy scripts/ops/comfy_ssh_forward.example.py and set COMFY_GPU_SSH_HOST/PORT" >&2
  exit 1
fi

pkill -f "$SCRIPT" 2>/dev/null || true
sleep 1
nohup "$VENV_PY" "$SCRIPT" "$LISTEN" "$PASSFILE" >>"$LOG" 2>&1 &
echo "started pid=$! log=$LOG"
sleep 2
pgrep -af "$SCRIPT" || { echo "not running"; tail -20 "$LOG" || true; exit 1; }
ss -lntp | grep ":${LISTEN} " || true
echo "check from client: curl -sS http://192.168.5.122:${LISTEN}/system_stats | head"
