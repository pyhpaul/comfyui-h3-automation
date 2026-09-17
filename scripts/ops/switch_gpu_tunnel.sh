#!/usr/bin/env bash
# From WSL/orchestration host: point vm122:8190 → GPU Comfy 127.0.0.1:8188.
#
# Required (never commit secrets):
#   COMFY_GPU_SSH_HOST
#   COMFY_GPU_SSH_PORT
#   COMFY_GPU_SSH_PASS   or  COMFY_GPU_SSH_PASSFILE
#
# Optional: VM122_SSH=vm122  COMFY_TUNNEL_LISTEN=8190
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VM122_SSH="${VM122_SSH:-vm122}"
LISTEN="${COMFY_TUNNEL_LISTEN:-8190}"
HOST="${COMFY_GPU_SSH_HOST:?set COMFY_GPU_SSH_HOST}"
PORT="${COMFY_GPU_SSH_PORT:?set COMFY_GPU_SSH_PORT}"
EXAMPLE="$ROOT/scripts/ops/comfy_ssh_forward.example.py"

if [[ -n "${COMFY_GPU_SSH_PASSFILE:-}" ]]; then
  PASS="$(tr -d '\r\n' <"$COMFY_GPU_SSH_PASSFILE")"
elif [[ -n "${COMFY_GPU_SSH_PASS:-}" ]]; then
  PASS="$COMFY_GPU_SSH_PASS"
else
  echo "set COMFY_GPU_SSH_PASS or COMFY_GPU_SSH_PASSFILE" >&2
  exit 1
fi

PASS_TMP="$(mktemp)"
trap 'rm -f "$PASS_TMP"' EXIT
umask 077
printf '%s' "$PASS" >"$PASS_TMP"
chmod 600 "$PASS_TMP"

scp -q "$EXAMPLE" "${VM122_SSH}:/tmp/comfy_ssh_forward.py"
scp -q "$PASS_TMP" "${VM122_SSH}:/tmp/.comfy_gpu_ssh_pass"
ssh -o BatchMode=yes "$VM122_SSH" "chmod 600 /tmp/.comfy_gpu_ssh_pass"

ssh -o BatchMode=yes "$VM122_SSH" \
  env "COMFY_GPU_SSH_HOST=$HOST" "COMFY_GPU_SSH_PORT=$PORT" "COMFY_TUNNEL_LISTEN=$LISTEN" \
  bash -s <<'REMOTE'
set -euo pipefail
HOST="${COMFY_GPU_SSH_HOST:?}"
PORT="${COMFY_GPU_SSH_PORT:?}"
LISTEN="${COMFY_TUNNEL_LISTEN:-8190}"

pkill -f '/tmp/comfy_ssh_forward.py' 2>/dev/null || true
pkill -f "ssh -N -p .* -L .*:${LISTEN}:127.0.0.1:8188" 2>/dev/null || true
fuser -k "${LISTEN}/tcp" 2>/dev/null || true
sleep 1

if [[ ! -x /tmp/comfy-fwd-venv/bin/python ]]; then
  python3 -m venv /tmp/comfy-fwd-venv
  /tmp/comfy-fwd-venv/bin/pip -q install paramiko
fi

python3 - <<PY
from pathlib import Path
import os, re
p = Path("/tmp/comfy_ssh_forward.py")
t = p.read_text()
host = os.environ["COMFY_GPU_SSH_HOST"]
port = int(os.environ["COMFY_GPU_SSH_PORT"])
t = re.sub(r'SSH_HOST = "[^"]+"', f'SSH_HOST = "{host}"', t)
t = re.sub(r"SSH_PORT = \d+", f"SSH_PORT = {port}", t)
p.write_text(t)
print("patched", host, port)
PY

: > /tmp/comfy_ssh_forward.log
nohup env COMFY_GPU_SSH_HOST="$HOST" COMFY_GPU_SSH_PORT="$PORT" \
  /tmp/comfy-fwd-venv/bin/python /tmp/comfy_ssh_forward.py "$LISTEN" /tmp/.comfy_gpu_ssh_pass \
  >>/tmp/comfy_ssh_forward.log 2>&1 &
echo "fwd_pid=$!"
sleep 3
pgrep -af comfy_ssh_forward || { tail -40 /tmp/comfy_ssh_forward.log; exit 1; }
ss -lntp | grep ":${LISTEN} " || true
curl -sS --max-time 20 "http://127.0.0.1:${LISTEN}/system_stats" | head -c 240
echo
REMOTE

echo "WSL check:"
curl -sS --max-time 20 "http://192.168.5.122:${LISTEN}/system_stats" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('ok',(d.get('devices')or[{}])[0].get('name'))"
