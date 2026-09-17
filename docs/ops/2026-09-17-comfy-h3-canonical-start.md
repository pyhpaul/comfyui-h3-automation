# 租卡 ComfyUI 正式启动 + vm122 映射（固化）

**日期：** 2026-09-17  
**原则：** H3 出片只用本文件约定的启动方式；密码/日更 SSH **不上库**。

## 拓扑

```text
WSL/Agent  →  http://192.168.5.122:8190  →  (vm122 SSH 隧道)
                                      →  租卡 127.0.0.1:8188  ComfyUI (H3)
```

## 租卡侧（唯一启动方式）

目录：`/root/autodl-tmp/ComfyUI` + `.venv`  
**不要**用平台 `/root/restart.sh`（会起 `/root/ComfyUI`、`--listen 0.0.0.0`、Triton 等，与编排不一致）。

仓库脚本（拷到租卡或经 `remote_comfy_h3.sh` 上传）：

| 脚本 | 作用 |
|------|------|
| `scripts/ops/comfy_gpu_status.sh` | 查 main.py / 8188 / socat 6006 |
| `scripts/ops/comfy_gpu_stop.sh` | **可选**停止；勿并入启动流程 |
| `scripts/ops/comfy_gpu_start.sh` | 正式启动（listen 127.0.0.1 + lowvram/fp16…） |

正式参数摘要：

```bash
python main.py \
  --listen 127.0.0.1 --port 8188 --cuda-device 0 \
  --lowvram --reserve-vram 4 --disable-smart-memory \
  --force-fp16 --disable-cuda-graphs --enable-manager
```

日志默认：`/root/autodl-tmp/ComfyUI/comfyUI-h3.log`  
租卡上也可：`/root/start_comfy_h3.sh`（与 `comfy_gpu_start.sh` 同内容）。

## 换机 / 开机标准流程（编排机 WSL）

```bash
cd /home/linux_dev/projects/comfyui-h3-automation
export COMFY_GPU_SSH_HOST='….chenyu.cn'
export COMFY_GPU_SSH_PORT='23076'
export COMFY_GPU_SSH_PASS='…'   # 或 PASSFILE，勿提交 git

# 1) 租卡：停旧进程 → 正式启动
bash scripts/ops/remote_comfy_h3.sh restart

# 2) vm122：8190 指到新机
bash scripts/ops/switch_gpu_tunnel.sh

# 3) 验证
export COMFY_BASE_URL=http://192.168.5.122:8190
curl -sS "$COMFY_BASE_URL/system_stats" | head
# 期望：devices 含 RTX 5090（或当日卡型），且队列可用
```

## vm122 落点（仍不入库）

| 路径 | 用途 |
|------|------|
| `/tmp/comfy_ssh_forward.py` | 转发（可由 `comfy_ssh_forward.example.py` 覆盖） |
| `/tmp/.comfy_gpu_ssh_pass` | 密码，mode 600 |
| `/tmp/comfy-fwd-venv` | paramiko |
| `/tmp/comfy_ssh_forward.log` | 日志 |

## 注意

- 租卡重启后若平台又跑起 `/root/restart.sh`，需再执行 `remote_comfy_h3.sh restart`。
- `socat :6006` 与 H3 出片无关；status 里仅作诊断。
- GPU 注意力双配置见 `docs/ops/2026-09-16-gpu-dual-profile.md`（5090/4080）。
