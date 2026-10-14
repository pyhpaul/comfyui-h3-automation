---
name: comfy-h3-env
description: >-
  Configures and verifies ComfyUI H3 access via COMFY_BASE_URL, vm106:8190→GPU:8188
  tunnel, and documents media upload (/upload/image) and download (/view) paths.
  Use before EP pack runs, when doctor fails, ports are unclear, upload/download
  landing paths need checking, or a finished Chenyu pod must be shut down.
---

# Comfy H3 Environment (ports & transfer)

## Always

1. Read [reference-env.md](reference-env.md).
2. Set and verify:

```bash
export COMFY_BASE_URL=http://192.168.50.106:8190
export PYTHONPATH=src
comfy-orch doctor
```

Use `.worktrees/feat-orch/.venv`. System python often lacks paramiko and impacket.

3. Refuse to submit H3 jobs if doctor/tunnel fails — fix the forwarder on **vm106** first. See `.cursor/rules/h3-gpu-vm106.mdc`.
4. Every Chenyu boot needs the environment prepared again. The platform start does not survive. Restart canonical Comfy, bring the tunnel back, then doctor, before any queue.

## Port map (memorize)

- **H3 out-film:** `192.168.50.106:8190` → GPU Comfy `127.0.0.1:8188`
- **CPU Comfy `:8188`:** retired — do not start; use 8190 only
- GPU SSH password stays in `/home/linux_dev/.config/fnos/.chenyu-gpu.pass` (mode 600). The tunnel copy on vm106 is `/tmp/.comfy_gpu_ssh_pass`. **Never** commit or print it.

## Transfer

- **Up:** local job assets → `POST /upload/image` → Comfy `input/` filenames in graph
- **Down:** history outputs → `GET /view`, then the four film files go to Feiniu. Do not keep a Downloads copy.

## Chenyu shutdown

When the user asked to shut the current pod down after the queue, start `scripts/ops/watch_feiniu_then_shutdown.py` in its own process at queue start. Do not wait for a later reminder. The watcher waits for the runner pid, then shuts down only after a clean `BATCH_DONE`, exit marker `:0`, four Feiniu files on every planned unit, and an empty `/queue`. `ARCHIVE_FAILED`, missing files, or a busy queue prints `HOLD` and does not click. The `podExample` tab must stay open. The page instance id omits a short suffix of the SSH hostname. The click itself is still `关机` then `确 定`, never `重启`, `另存储为镜像并关机`, or `关机并销毁`. Contract: [reference-env.md](reference-env.md) and `.cursor/rules/h3-gpu-vm106.mdc`.

## Gate

- [ ] `COMFY_BASE_URL` points at **8190** for GPU H3
- [ ] `/system_stats` shows CUDA device
- [ ] Agent knows upload is HTTP API (not manual scp) for normal EP flow
- [ ] Agent knows finished films go to Feiniu, not Downloads
