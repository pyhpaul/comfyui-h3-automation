---
name: comfy-h3-env
description: >-
  Configures and verifies ComfyUI H3 access via COMFY_BASE_URL, vm122:8190→GPU:8188
  tunnel, and documents media upload (/upload/image) and download (/view) paths.
  Use before EP pack runs, when doctor fails, ports are unclear, or upload/download
  landing paths need checking.
---

# Comfy H3 Environment (ports & transfer)

## Always

1. Read [reference-env.md](reference-env.md).
2. Set and verify:

```bash
export COMFY_BASE_URL=http://192.168.5.122:8190
comfy-orch doctor
```

3. Refuse to submit H3 jobs if doctor/tunnel fails — fix forwarder on **vm122** first (`docs/HANDOFF.md`, `scripts/ops/`, `docs/ops/2026-09-09-gpu-comfy-api-archive.md`).

## Port map (memorize)

- **H3 out-film (shared):** `192.168.5.122:8190` → GPU Comfy `127.0.0.1:8188` — all handoff users use this URL
- **CPU Comfy `:8188`:** retired — do not start; use 8190 only
- Passwords stay on vm122 `/tmp/.comfy_gpu_ssh_pass` (mode 600) — **never** commit

## Transfer

- **Up:** local job assets → `POST /upload/image` → Comfy `input/` filenames in graph
- **Down:** history outputs → `GET /view` → `outputs/<job_id>/` (+ optional Downloads copy)

## Gate

- [ ] `COMFY_BASE_URL` points at **8190** for GPU H3
- [ ] `/system_stats` shows CUDA device
- [ ] Agent knows upload is HTTP API (not manual scp) for normal EP flow
- [ ] Agent knows pull lands under repo `outputs/` then optional `/mnt/c/Users/lxy/Downloads/`
