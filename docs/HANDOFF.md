# 交接手册（HANDOFF）

面向：**在 WSL/本机编排 + 经 vm106 访问租卡 ComfyUI（MiniMax H3）** 的接手人。  
仓库：`comfyui-h3-automation`。密码/密钥**不要**提交进 git。当前部署和关机以 `.cursor/rules/h3-gpu-vm106.mdc` 为准。

## 1. 拓扑（固定）

```text
编排机 (WSL/Agent)
    │  HTTP
    ▼
vm106  192.168.50.106:8190
    │  SSH 隧道 (用户态转发)
    ▼
租卡  127.0.0.1:8188   (ComfyUI + H3，仅本机监听)
```

| 项 | 值 |
|----|-----|
| 编排 URL | `export COMFY_BASE_URL=http://192.168.50.106:8190` |
| 浏览器 Comfy | 同上 `http://192.168.50.106:8190`（须与 API 同实例） |
| ~~vm122:8190 / vm122:8188~~ | **已停用** |
| vm106 SSH | `Host vm106` → `192.168.50.106`，用户 `pyh` |
| 租卡 SSH | 每次开机变；向用户要主机和端口；**不要写进仓库** |
| 租卡密码 | `/home/linux_dev/.config/fnos/.chenyu-gpu.pass`，权限 600 |

## 2. 租卡 Comfy 正式启动 + vm106 映射（接手必会）

**唯一 H3 启动方式**见：`docs/ops/2026-09-17-comfy-h3-canonical-start.md`  
（`127.0.0.1:8188` + lowvram/fp16…；**不用**平台 `/root/restart.sh`。）

转发跑在 **vm106** 上，不是 WSL：

| 路径 | 用途 |
|------|------|
| `/tmp/comfy_ssh_forward.py` | 监听 `8190` → 租卡 `127.0.0.1:8188` |
| `/tmp/.comfy_gpu_ssh_pass` | 租卡密码，权限 **600** |
| `/tmp/comfy-fwd-venv` | 含 `paramiko` 的 venv |
| `/tmp/comfy_ssh_forward.log` | 日志 |

仓库脚本：

- `scripts/ops/comfy_gpu_{status,stop,start}.sh` — 租卡侧
- `scripts/ops/remote_comfy_h3.sh` — WSL 远程启停
- `scripts/ops/switch_gpu_tunnel.sh` — WSL 切 vm106:8190（`VM122_SSH=vm106`）
- `scripts/ops/comfy_ssh_forward.example.py` / `restart_comfy_tunnel.sh`

### 换租卡（每天常见）

在 **WSL**（能 `ssh vm106`）上：

```bash
cd /home/linux_dev/projects/comfyui-h3-automation
export COMFY_GPU_SSH_HOST='<host>.chenyu.cn'
export COMFY_GPU_SSH_PORT='<port>'
export COMFY_GPU_SSH_PASSFILE=/home/linux_dev/.config/fnos/.chenyu-gpu.pass
export VM122_SSH=vm106
export PATH="/home/linux_dev/projects/comfyui-h3-automation/.worktrees/feat-orch/.venv/bin:$PATH"

bash scripts/ops/remote_comfy_h3.sh restart
bash scripts/ops/switch_gpu_tunnel.sh
curl -sS http://192.168.50.106:8190/system_stats | head
```

期望：JSON 里有 `devices` / CUDA。`Connection reset` → 转发未起、租卡 SSH 不通、或 Comfy 未按正式参数监听 `127.0.0.1:8188`。

成片都在飞牛、`/queue` 为空、没有入队进程之后，用户说关机再关。入队脚本不会自己关机。用户说了跑完再关，入队一开始就要另起等待进程，不要等下一次对话被提醒：

```bash
PYTHONPATH=src python scripts/ops/watch_feiniu_then_shutdown.py \
  --pid <入队进程> --log <入队日志> --exit-marker '<EXIT 前缀>' \
  --ssh-host '<id>.gz15.chenyu.cn' --feiniu-batch '<批次>' \
  --episode EP01 --units U01 U02
```

日志不干净、飞牛缺文件或队列不空时，等待进程打印 `HOLD` 并不关机。用已经开着的晨羽页，不要新开标签，页要一直开着。直接点关机仍是：

```bash
python3 scripts/ops/chenyu_shutdown.py <ssh-host>
```

只点文字正好是 `关机` 的按钮，确认 `关机确认` 后点 `确定`。不要点 `重启`、`另存储为镜像并关机`、`关机并销毁`。成功打印 `OFF`。细节见 `.cursor/rules/h3-gpu-vm106.mdc`。

## 3. 开工硬门禁（不用再问）

每次开跑 / 续跑前不用再问模式。采数默认 **只一采**。没有明确说二采，不要加 `--second-pass`。场景连续时用 **`motion_latent`**。换场、`start_mode=independent`、或上一条已经是上下分屏，都不接上一条的 latent。只有明确说整片参考才用 `ref_video`。详见 `docs/ops/2026-09-10-render-profiles.md`、规则 `.cursor/rules/h3-render-mode-gate.mdc`、`.cursor/rules/h3-queue-run.mdc`。

**Manual-call 日常默认（已固化）：** `motion_latent` + **无二采** + `gpu-profile auto` — 见 `docs/ops/2026-09-17-h3-manual-call-run-defaults.md` 与 `scripts/ops/run_ep_manual_call_defaults.sh`。

工程加强（无脸检测暂缓）：`comfy_orch.named_assets_bind` 剧名绑定标签 + 按集 latent 前缀 `h3_context/epXX_uYY`；审核列 `inject=`/`reorder=`/`unbound=`；刷新已有 job：`python scripts/ops/refresh_manual_call_bind_labels.py --glob '…-U*'`。

日常命令（只一采 + 场景连续 + 飞牛）：

```bash
export COMFY_BASE_URL=http://192.168.50.106:8190
export PYTHONPATH=src
cd /home/linux_dev/projects/comfyui-h3-automation
source .worktrees/feat-orch/.venv/bin/activate

python scripts/run_ep_units_profiled.py --units U01 U02 \
  --continuity motion_latent \
  --feiniu-batch '<批次>'
```

`motion_latent` 在 GPU latent 路径出来后打印 `HANDOFF` 并马上入下一条，飞牛上传在后台。`/queue` 空而日志仍是 `queue=running`，是本地归档空隙，不是暂停。已经 `success` 或飞牛上已经有四个文件的单元不要重入队。见 `.cursor/rules/h3-queue-run.mdc`。

只有这次明确说整片参考才把 `--continuity` 改成 `ref_video`。只有这次明确说二采才加 `--second-pass`。不要传 `--download-dir`。

## 4. 资产包 → Job

```bash
python scripts/ep_pack_to_jobs.py <PACK> -o jobs/ep_units --unit U01
python scripts/audit_pack_prompts.py   # EP02：no_parent + with_parent
```

| pack_kind | 特征 | 提示词策略 |
|-----------|------|------------|
| `ep02_causality` | `manifest.json` + `ep02/prompts/` | **wire-only**：只换 `<Picture N>` / `<Video 1>` |
| `h3_latent` | EP01 latent zip | 转换器路径（legacy） |
| `seedance_upload` | EP03/EP04 `upload-manifest.json` | 可走六段英文转换（legacy） |

`jobs/` **默认不入库**（含素材）；接手人用包现场生成。模板在 `templates/yz_h3_ep_unit/`。

## 5. 前端显式（画布）

`/prompt` **不会**改 Comfy 画布控件。要给人看槽位/提示词：

```bash
python scripts/export_bound_workflow.py jobs/ep_units/<JOB> \
  -o /mnt/c/Users/lxy/Downloads/<name>-bound-api.json \
  --out-ui /mnt/c/Users/lxy/Downloads/<name>-bound-ui.json
```

在浏览器打开 **8190**，Load **UI** JSON（不要只 Load API JSON 谈布局）。

## 6. 参数（常用）

| 字段 / 手段 | 作用 |
|-------------|------|
| `job.yaml` → `duration_seconds` / `aspect_ratio` / `megapixels` | 时长与分辨率选择器 |
| `mystic_lora_strength` | MysticXXX LoRA（node 128）；EP02 U05+ 曾用 `0.5`，U01–U04 常用默认 `0.2` |
| `--pass2-scale` | 二采升采样倍数，默认 `1.5` |
| `filename_prefix` | 成片前缀；profiled 模式下会变成 `*-pass1` / `*-pass2` |

绑定表：`templates/yz_h3_ep_unit/bindings.yaml`。

## 7. 数据上/下载

| 方向 | API | 落点 |
|------|-----|------|
| 上 | `POST /upload/image` | 租卡 Comfy `input/` |
| 下成片 | `GET /history/{id}` → `GET /view` → 飞牛 | `H3_comfyUI_5090/archive/<批次>/<集>/<单元>/` 四个文件。不留 Downloads |
| 下 latent | Motion Context 槽位如 `h3_context/ep02_u01_00001.safetensors` | `/view?subfolder=h3_context&type=output` |

正常流程**不需要** scp 素材到租卡。

## 8. Agent Skills 地图

| Skill | 阶段 |
|-------|------|
| `comfy-h3-ep-pipeline` | 总控 + 模式门禁 |
| `comfy-h3-env` | 端口 / doctor |
| `comfy-h3-ep-pack-jobs` | 包 → job |
| `comfy-h3-pack-prompt-audit` | EP02 wire-only 审核 |
| `comfy-h3-bound-export` | 画布可见导出 |
| `comfy-h3-queue-pull` | 单 job 入队监控拉片 |

路径：`.cursor/skills/<name>/SKILL.md`。

## 9. 验收命令

```bash
export COMFY_BASE_URL=http://192.168.50.106:8190
comfy-orch doctor
python -m pytest -q
python scripts/audit_pack_prompts.py
```

## 10. 常见坑

| 现象 | 处理 |
|------|------|
| `:8190` reset / 无 CUDA | 在 vm106 重启转发；检查租卡 SSH host/port/密码 |
| 误用 `:8188` | 旧 CPU Comfy，已停 |
| 二采 + Motion Context shape mismatch | 二采须用独立 guider（现 `render_profile` 已处理） |
| history 无 latent 路径 | 槽位文件仍可能在 `h3_context/*_0000N.safetensors`；用 `--parent-latent` 续跑 |
| OOM | 先保一采+latent；二采降 `--pass2-scale` 或拆开跑 |
| 画布空白 | 需要 bound UI Load，不是只 queue |

## 11. 相关文档

- 部署与关机：`.cursor/rules/h3-gpu-vm106.mdc`、`docs/ops/2026-09-17-comfy-h3-canonical-start.md`
- 入队接力：`.cursor/rules/h3-queue-run.mdc`
- 拆包：`.cursor/rules/h3-pack-prep.mdc`
- 飞牛：`.cursor/rules/h3-feiniu-archive-only.mdc`
- 一采 vs 二采 / latent：`docs/ops/2026-09-10-render-profiles.md`
- 租卡 API 归档：`docs/ops/2026-09-09-gpu-comfy-api-archive.md`
- 端到端（偏 EP 包）：`docs/ops/2026-09-09-ep-pack-to-video-pipeline.md`
- EP03/EP04 包字段：`docs/ops/2026-09-09-ep03-ep04-yz-pack.md`
