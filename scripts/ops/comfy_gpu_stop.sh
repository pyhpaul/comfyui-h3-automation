#!/usr/bin/env bash
# Run ON the GPU rental host.
# Optional stop: only when you intentionally stop ComfyUI / 6006 mapping.
# Do NOT put this in the normal start path.
set -euo pipefail

pkill -f "python.*main.py" 2>/dev/null || true
pkill -f "socat TCP-LISTEN:6006" 2>/dev/null || true
fuser -k 8188/tcp 2>/dev/null || true
sleep 1
ss -lntp | grep -E ':8188|:6006' || echo "ComfyUI 和 socat 都已停止"
pgrep -af "python.*main.py" || echo "ComfyUI 进程不存在"
