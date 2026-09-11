# Environment: port mapping & data up/download

Do **not** put SSH passwords in skills, git, or argv. Prefer keys / existing tunnel on vm122.

## Topology (H3 out-film path)

```text
WSL / agent  ──HTTP──►  vm122:8190  ──SSH tunnel──►  GPU box 127.0.0.1:8188  (ComfyUI + H3)
                              │
                              └── COMFY_BASE_URL=http://192.168.5.122:8190
```

| Role | Address | Notes |
|------|---------|--------|
| Orchestration Base URL | `http://192.168.5.122:8190` | **Only** URL jobs should use for H3 |
| Comfy on GPU | `127.0.0.1:8188` | Listen localhost only; not reachable from LAN/public |
| Tunnel hop | vm122 `0.0.0.0:8190` → GPU `:8188` | Script historically `/tmp/comfy_ssh_forward.py` on vm122 |
| Optional local forward | `ssh -L 127.0.0.1:8190:127.0.0.1:8188 -p <ssh_port> root@<gpu-host>` | Then `COMFY_BASE_URL=http://127.0.0.1:8190` |

### Do not confuse with CPU/dev Comfy

| Env | Typical URL | Use |
|-----|-------------|-----|
| GPU H3 (tunnel) | `…:8190` | Real YZ/H3 out-film |
| vm122 CPU Comfy | `http://192.168.5.122:8188` | **已停用**；统一用 8190 |

Wrong Base URL → missing nodes or no GPU.

## Doctor before work

```bash
export COMFY_BASE_URL=http://192.168.5.122:8190
comfy-orch doctor    # or GET /system_stats
```

Expect JSON with `devices` / CUDA. Connection refused → fix tunnel on vm122 first (see `docs/ops/2026-09-09-gpu-comfy-api-archive.md`).

## Data: upload (local → Comfy input)

| Step | Mechanism | Detail |
|------|-----------|--------|
| Pack → job | Local copy | EP files → `jobs/ep_units/EPxx-Uyy/assets/` |
| Job → Comfy | `POST {COMFY_BASE_URL}/upload/image` | `ComfyClient.upload_image`; multipart file + `overwrite` |
| What is uploaded | Bindings `media: true` | control / identity images, previz video (same upload endpoint), silent wav placeholders for empty audio |
| Remote result | Filename string | Written into workflow LoadImage / VHS widgets (e.g. `id1-char-001.png`) |
| Remote disk | Comfy `input/` | Server-side; agent does not scp for normal EP flow |

Upload retries: client default 3 attempts with backoff.

## Data: download (Comfy → local)

| Step | Mechanism | Detail |
|------|-----------|--------|
| Discover | `GET /history/{prompt_id}` | Read `outputs[*].(gifs\|videos\|images)[].filename` |
| Fetch | `GET /view?filename=&subfolder=&type=` | `type` often `temp` for VHS preview mp4 |
| Authority land | `outputs/<job_id>/` | Via `collect_outputs` |
| Human compare | `/mnt/c/Users/lxy/Downloads/<dir>/` | Optional copy + PRIOR_*.mp4 + prompt_h3.txt |

YZ one-pass name pattern example: `YZ_H3_一采_XXXXX-audio.mp4` (counter is server-side, not episode id).

## Paths cheat sheet

| Kind | Path |
|------|------|
| Repo | `/home/linux_dev/projects/comfyui-h3-automation` |
| EP packs (example) | `/tmp/ep02_assets/EP03` |
| Jobs | `jobs/ep_units/EP03-U01/` |
| Run status | `runs/<job_id>/status.json` |
| Outputs | `outputs/<job_id>/` |
| Windows Downloads (WSL) | `/mnt/c/Users/lxy/Downloads/` |
| Bound UI for Load | same Downloads `*-yz-bound-ui*.json` |

## Browser vs API

- Browser Comfy must target the **same** instance as `COMFY_BASE_URL` (open `http://192.168.5.122:8190` when using the tunnel).
- API upload/prompt does not refresh canvas; Load bound UI after upload to see slots.

## Failure hints

| Symptom | Likely cause |
|---------|----------------|
| Connection refused / disconnect mid-poll | Tunnel down or SSH drop — resume by `prompt_id`, repair forwarder |
| Works on 8188, YZ nodes missing | Pointed at CPU Comfy, not 8190 GPU |
| Upload OK, empty pull | History not success yet, or wrong `type`/`subfolder` on `/view` |
| Duplicate submit | Monitor died but job still running — check `/queue` before re-queue |
