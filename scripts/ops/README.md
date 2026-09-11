# Ops scripts for vm122 Comfy tunnel

These run on **vm122** (`192.168.5.122`), shared by everyone who uses `COMFY_BASE_URL=http://192.168.5.122:8190`.

1. Create venv once: `python3 -m venv /tmp/comfy-fwd-venv && /tmp/comfy-fwd-venv/bin/pip install paramiko`
2. Copy `comfy_ssh_forward.example.py` → `/tmp/comfy_ssh_forward.py` (or set `COMFY_FWD_SCRIPT`)
3. `export COMFY_GPU_SSH_HOST=... COMFY_GPU_SSH_PORT=...`
4. Password file `/tmp/.comfy_gpu_ssh_pass` mode `600`
5. `bash restart_comfy_tunnel.sh`

Full handoff: `docs/HANDOFF.md` §2.
