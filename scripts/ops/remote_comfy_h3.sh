#!/usr/bin/env bash
# From WSL: remote status / stop / start of canonical H3 Comfy on the rental GPU.
#
# Usage:
#   export COMFY_GPU_SSH_HOST=... COMFY_GPU_SSH_PORT=...
#   export COMFY_GPU_SSH_PASS='...'   # or PASSFILE
#   bash scripts/ops/remote_comfy_h3.sh status
#   bash scripts/ops/remote_comfy_h3.sh stop
#   bash scripts/ops/remote_comfy_h3.sh start
#   bash scripts/ops/remote_comfy_h3.sh restart   # stop + start
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ACTION="${1:?usage: remote_comfy_h3.sh status|stop|start|restart}"
HOST="${COMFY_GPU_SSH_HOST:?set COMFY_GPU_SSH_HOST}"
PORT="${COMFY_GPU_SSH_PORT:?set COMFY_GPU_SSH_PORT}"

if [[ -n "${COMFY_GPU_SSH_PASSFILE:-}" ]]; then
  PASS="$(tr -d '\r\n' <"$COMFY_GPU_SSH_PASSFILE")"
elif [[ -n "${COMFY_GPU_SSH_PASS:-}" ]]; then
  PASS="$COMFY_GPU_SSH_PASS"
else
  echo "set COMFY_GPU_SSH_PASS or COMFY_GPU_SSH_PASSFILE" >&2
  exit 1
fi

python3 - "$ACTION" "$HOST" "$PORT" "$PASS" "$ROOT" <<'PY'
from __future__ import annotations
import base64, sys, time
from pathlib import Path
import paramiko

action, host, port_s, password, root = sys.argv[1:6]
port = int(port_s)
ops = Path(root) / "scripts" / "ops"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(host, port=port, username="root", password=password, timeout=25,
          allow_agent=False, look_for_keys=False)

def run(cmd: str, timeout: int = 180) -> tuple[int, str]:
    _, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    text = out if out.strip() else err
    return code, text

def upload_script(local_name: str, remote: str) -> None:
    body = (ops / local_name).read_bytes()
    b64 = base64.b64encode(body).decode()
    run(f"echo {b64} | base64 -d > {remote} && chmod +x {remote}")

upload_script("comfy_gpu_status.sh", "/root/comfy_gpu_status.sh")
upload_script("comfy_gpu_stop.sh", "/root/comfy_gpu_stop.sh")
upload_script("comfy_gpu_start.sh", "/root/start_comfy_h3.sh")

def status() -> None:
    code, text = run("bash /root/comfy_gpu_status.sh")
    print(text)
    raise SystemExit(code)

def stop() -> None:
    code, text = run("bash /root/comfy_gpu_stop.sh")
    print(text)
    raise SystemExit(code)

def start() -> None:
    # ensure stopped first is caller's job for restart; start alone assumes free port
    cmd = r'''
set -e
: > /root/autodl-tmp/ComfyUI/comfyUI-h3.log
nohup bash /root/start_comfy_h3.sh >/dev/null 2>&1 &
echo start_pid=$!
for i in $(seq 1 60); do
  if ss -lntp | grep -q '127.0.0.1:8188'; then
    echo LISTEN_OK at ${i}s
    break
  fi
  sleep 2
done
bash /root/comfy_gpu_status.sh
curl -sS --max-time 15 http://127.0.0.1:8188/system_stats | head -c 220; echo
'''
    code, text = run(cmd, timeout=200)
    print(text)
    if "LISTEN_OK" not in text and "127.0.0.1:8188" not in text:
        raise SystemExit(1)
    raise SystemExit(code)

if action == "status":
    status()
elif action == "stop":
    stop()
elif action == "start":
    start()
elif action == "restart":
    _, text = run("bash /root/comfy_gpu_stop.sh")
    print(text)
    time.sleep(2)
    start()
else:
    raise SystemExit(f"unknown action: {action}")
PY
