#!/usr/bin/env bash
# Run ON the GPU rental host. Canonical status probe for H3 Comfy.
set -euo pipefail

echo "========== ComfyUI 进程 =========="
pgrep -af "python.*main.py" || echo "ComfyUI 进程不存在"

echo
echo "========== ComfyUI 8188 端口 =========="
ss -lntp | grep ':8188' || echo "8188 未监听"

echo
echo "========== socat 进程 =========="
pgrep -af "socat.*6006" || echo "socat 进程不存在"

echo
echo "========== socat 6006 端口 =========="
ss -lntp | grep ':6006' || echo "6006 未监听"
