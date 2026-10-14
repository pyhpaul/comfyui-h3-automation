# Environment: port mapping & data up/download

Do **not** put SSH passwords in skills, git, or argv. The tunnel runs on vm106.

## Topology (H3 out-film path)

```text
WSL / agent  ──HTTP──►  vm106:8190  ──SSH tunnel──►  GPU box 127.0.0.1:8188  (ComfyUI + H3)
                              │
                              └── COMFY_BASE_URL=http://192.168.50.106:8190
```

| Role | Address | Notes |
|------|---------|--------|
| Orchestration Base URL | `http://192.168.50.106:8190` | Jobs use this URL for H3 |
| Comfy on GPU | `127.0.0.1:8188` | Listen localhost only; not reachable from LAN/public |
| Tunnel hop | vm106 `0.0.0.0:8190` → GPU `:8188` | `/tmp/comfy_ssh_forward.py` on vm106. `VM122_SSH=vm106` |
| Optional local forward | `ssh -L 127.0.0.1:8190:127.0.0.1:8188 -p <ssh_port> root@<gpu-host>` | Then `COMFY_BASE_URL=http://127.0.0.1:8190` |

### Do not confuse with CPU/dev Comfy

| Env | Typical URL | Use |
|-----|-------------|-----|
| GPU H3 (tunnel) | `http://192.168.50.106:8190` | Real YZ/H3 out-film |
| vm122 CPU Comfy | `http://192.168.5.122:8188` | **已停用**；vm122 也不再做隧道 |

Wrong Base URL → missing nodes or no GPU.

## Doctor before work

```bash
export COMFY_BASE_URL=http://192.168.50.106:8190
comfy-orch doctor    # or GET /system_stats
```

Expect JSON with `devices` / CUDA. Connection refused → fix the tunnel on vm106 first. Deploy and shutdown steps: `.cursor/rules/h3-gpu-vm106.mdc`.

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
| Authority land | Feiniu `H3_comfyUI_5090/archive/<批次>/<集>/<单元>/` | mp4, latent, `prompt_h3.txt`, `run_meta.json` |
| Local status | `runs/<job_id>/status.json` | Run record. Not the film |

YZ one-pass name pattern example: `YZ_H3_一采_XXXXX-audio.mp4` (counter is server-side, not episode id).

## Paths cheat sheet

| Kind | Path |
|------|------|
| Repo | `/home/linux_dev/projects/comfyui-h3-automation` |
| EP packs (example) | `/tmp/ep02_assets/EP03` |
| Jobs | `jobs/ep_units/EP03-U01/` |
| Run status | `runs/<job_id>/status.json` |
| Films | Feiniu archive, not `outputs/` or Downloads |
| Windows Downloads (WSL) | bound UI JSON only, not films |
| Bound UI for Load | same Downloads `*-yz-bound-ui*.json` |

## Browser vs API

- Browser Comfy must target the **same** instance as `COMFY_BASE_URL` (open `http://192.168.50.106:8190` when using the tunnel).
- API upload/prompt does not refresh canvas; Load bound UI after upload to see slots.

## Chenyu pod shutdown

Use the Chrome tab the user already has open at `https://www.chenyu.cn/console/podExample`. CDP proxy is `http://localhost:3456`. Do not open a second tab and do not close theirs.

```bash
python3 scripts/ops/chenyu_shutdown.py <ssh-host>
```

Wait until every planned unit is on Feiniu (mp4, latent, `prompt_h3.txt`, `run_meta.json`), no queue runner is alive, and Comfy `/queue` is empty. Then run the script. It refuses to click when the page instance is a different machine. Success prints `OFF`.

The console `实例ID` is the SSH label with a short hex suffix removed. `ee58bde62caf457e810680ba64e7cbe571.gz15.chenyu.cn` is shown as `ee58bde62caf457e810680ba64e7cbe5`. On 2026-10-08 a check for the full hostname returned `WRONG_INSTANCE` and exited before clicking. Do not require `.gzNN.chenyu.cn` or the extra suffix to appear in `innerText`.

Click `div.operateItem` whose trimmed text is exactly `关机`. The dialog title is `关机确认`. Its primary button text is `确 定` with a space, so compare after removing whitespace. A successful confirm changes `运行状态` to `关机中`. GPU billing stops then. The page may show a long backup time. The instance and its disk are kept. Seven days unused and the platform releases it.

## Failure hints

| Symptom | Likely cause |
|---------|----------------|
| Connection refused / disconnect mid-poll | Tunnel down or SSH drop — resume by `prompt_id`, repair forwarder |
| Works on 8188, YZ nodes missing | Pointed at CPU Comfy, not 8190 GPU |
| Upload OK, empty pull | History not success yet, or wrong `type`/`subfolder` on `/view` |
| Duplicate submit | Monitor died but job still running — check `/queue` before re-queue |
