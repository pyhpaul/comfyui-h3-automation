# Ops：租卡 Comfy（H3）+ vm122 隧道

编排入口：`COMFY_BASE_URL=http://192.168.5.122:8190`。

## 固化流程（推荐）

详见 `docs/ops/2026-09-17-comfy-h3-canonical-start.md`。  
出片默认参数：`docs/ops/2026-09-17-h3-manual-call-run-defaults.md`。

| 脚本 | 在哪跑 | 作用 |
|------|--------|------|
| `comfy_gpu_status.sh` | 租卡 | 查进程 / 8188 / socat |
| `comfy_gpu_stop.sh` | 租卡 | 可选停止（勿并入启动） |
| `comfy_gpu_start.sh` | 租卡 | **正式** H3 启动参数 |
| `remote_comfy_h3.sh` | WSL | SSH 上租卡执行 status/stop/start/restart |
| `switch_gpu_tunnel.sh` | WSL | 把 vm122:8190 指到当前租卡 |
| `comfy_ssh_forward.example.py` | 部署到 vm122 `/tmp` | 8190→8188 转发 |
| `run_ep_manual_call_defaults.sh` | WSL | 锁定 `motion_latent` + 无二采 + `gpu-profile auto` |
| `h3_manual_call_run_defaults.env.example` | WSL | 上述默认的环境变量样例 |

```bash
export COMFY_GPU_SSH_HOST=….chenyu.cn COMFY_GPU_SSH_PORT=….
export COMFY_GPU_SSH_PASS='…'   # 不上库
bash scripts/ops/remote_comfy_h3.sh restart
bash scripts/ops/switch_gpu_tunnel.sh
```

## 仅隧道（旧步骤）

1. Create venv once: `python3 -m venv /tmp/comfy-fwd-venv && /tmp/comfy-fwd-venv/bin/pip install paramiko`
2. Copy `comfy_ssh_forward.example.py` → `/tmp/comfy_ssh_forward.py`
3. `export COMFY_GPU_SSH_HOST=... COMFY_GPU_SSH_PORT=...`
4. Password file `/tmp/.comfy_gpu_ssh_pass` mode `600`
5. `bash restart_comfy_tunnel.sh`

Full handoff: `docs/HANDOFF.md` §2。
