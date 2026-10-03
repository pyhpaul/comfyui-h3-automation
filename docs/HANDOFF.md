# 交接手册（HANDOFF）

面向：**在 WSL/本机编排 + 经 vm122 访问租卡 ComfyUI（MiniMax H3）** 的接手人。  
仓库：`comfyui-h3-automation`。密码/密钥**不要**提交进 git。

## 1. 拓扑（固定）

```text
编排机 (WSL/Agent)
    │  HTTP
    ▼
vm122  0.0.0.0:8190   ← 所有人共用的 Comfy 入口
    │  SSH 隧道 (用户态转发)
    ▼
租卡  127.0.0.1:8188   (ComfyUI + H3，仅本机监听)
```

| 项 | 值 |
|----|-----|
| 编排唯一 URL | `export COMFY_BASE_URL=http://192.168.5.122:8190` |
| 浏览器 Comfy | 同上 `http://192.168.5.122:8190`（须与 API 同实例） |
| ~~vm122:8188 CPU Comfy~~ | **已停用**，勿再用 |
| vm122 SSH（示例） | `Host vm122` → `192.168.5.122`（本机 `~/.ssh/config`） |
| 租卡 SSH | 每日可能变；见当日平台；**不要写进仓库** |

## 2. 租卡 Comfy 正式启动 + vm122 映射（接手必会）

**唯一 H3 启动方式**见：`docs/ops/2026-09-17-comfy-h3-canonical-start.md`  
（`127.0.0.1:8188` + lowvram/fp16…；**不用**平台 `/root/restart.sh`。）

转发跑在 **vm122** 上，不是 WSL：

| 路径 | 用途 |
|------|------|
| `/tmp/comfy_ssh_forward.py` | 监听 `8190` → 租卡 `127.0.0.1:8188` |
| `/tmp/.comfy_gpu_ssh_pass` | 租卡密码，权限 **600** |
| `/tmp/comfy-fwd-venv` | 含 `paramiko` 的 venv |
| `/tmp/comfy_ssh_forward.log` | 日志 |

仓库脚本：

- `scripts/ops/comfy_gpu_{status,stop,start}.sh` — 租卡侧
- `scripts/ops/remote_comfy_h3.sh` — WSL 远程启停
- `scripts/ops/switch_gpu_tunnel.sh` — WSL 切 vm122:8190
- `scripts/ops/comfy_ssh_forward.example.py` / `restart_comfy_tunnel.sh`

### 换租卡（每天常见）

在 **WSL**（能 `ssh vm122`）上：

```bash
cd /home/linux_dev/projects/comfyui-h3-automation
export COMFY_GPU_SSH_HOST='<host>.chenyu.cn'
export COMFY_GPU_SSH_PORT='<port>'
export COMFY_GPU_SSH_PASS='<password>'   # 勿提交 git；可用 PASSFILE

bash scripts/ops/remote_comfy_h3.sh restart
bash scripts/ops/switch_gpu_tunnel.sh
curl -sS http://192.168.5.122:8190/system_stats | head
```

期望：JSON 里有 `devices` / CUDA。`Connection reset` → 转发未起、租卡 SSH 不通、或 Comfy 未按正式参数监听 `127.0.0.1:8188`。

## 3. 开工硬门禁（先问再跑）

每次开跑 / 续跑前确认：

1. **只一采** 还是 **一采+二采**（`--second-pass`）？
2. 接力 **`ref_video`（整片）** 还是 **`motion_latent`（AV latent）**？

未确认不得提交。详见 `docs/ops/2026-09-10-render-profiles.md`、规则 `.cursor/rules/h3-render-mode-gate.mdc`。

**Manual-call 日常默认（已固化）：** `motion_latent` + **无二采** + `gpu-profile auto` — 见 `docs/ops/2026-09-17-h3-manual-call-run-defaults.md` 与 `scripts/ops/run_ep_manual_call_defaults.sh`。

工程加强（无脸检测暂缓）：`comfy_orch.named_assets_bind` 剧名绑定标签 + 按集 latent 前缀 `h3_context/epXX_uYY`；审核列 `inject=`/`reorder=`/`unbound=`；刷新已有 job：`python scripts/ops/refresh_manual_call_bind_labels.py --glob '…-U*'`。

| 模式 | 命令要点 | 产物目录建议分开 |
|------|----------|------------------|
| A 单纯一采 | `--continuity ref_video`（不要 `--second-pass`） | 如 `…-rewire` |
| B 因果+二采 | `--continuity motion_latent --second-pass` | 如 `…-latent-mc` |

```bash
export COMFY_BASE_URL=http://192.168.5.122:8190
cd /home/linux_dev/projects/comfyui-h3-automation
source .worktrees/feat-orch/.venv/bin/activate   # 或项目 .venv

python scripts/run_ep_units_profiled.py --units U01 U02 --continuity ref_video \
  --download-dir /mnt/c/Users/lxy/Downloads/<dir-a>

python scripts/run_ep_units_profiled.py --units U01 U02 \
  --continuity motion_latent --second-pass \
  --download-dir /mnt/c/Users/lxy/Downloads/<dir-b>
```

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
| 下成片 | `GET /history/{id}` → `GET /view` | 权威：`outputs/<job_id>/`；可选拷贝到 Windows Downloads |
| 下 latent | Motion Context 槽位如 `h3_context/ep02_u01_00001.safetensors` | `/view?subfolder=h3_context&type=output` |

正常流程**不需要** scp 素材到租卡。

## 8. Agent Skills 地图

| Skill | 阶段 |
|-------|------|
| `comfy-h3-ep-pipeline` | 总控 + 模式门禁 |
| `comfy-h3-env` | 端口 / doctor |
| `comfy-h3-feiniu` | 飞牛 NAS：inbox 资产包、archive 成片 |
| `comfy-h3-ep-pack-jobs` | 包 → job |
| `comfy-h3-pack-prompt-audit` | EP02 wire-only 审核 |
| `comfy-h3-bound-export` | 画布可见导出 |
| `comfy-h3-queue-pull` | 单 job 入队监控拉片 |

路径：`.cursor/skills/<name>/SKILL.md`。

## 9. 验收命令

```bash
export COMFY_BASE_URL=http://192.168.5.122:8190
comfy-orch doctor
python -m pytest -q
python scripts/audit_pack_prompts.py
```

## 10. 常见坑

| 现象 | 处理 |
|------|------|
| `:8190` reset / 无 CUDA | vm122 重启转发；检查租卡 SSH host/port/密码 |
| 误用 `:8188` | 旧 CPU Comfy，已停 |
| 二采 + Motion Context shape mismatch | 二采须用独立 guider（现 `render_profile` 已处理） |
| history 无 latent 路径 | 槽位文件仍可能在 `h3_context/*_0000N.safetensors`；用 `--parent-latent` 续跑 |
| OOM | 先保一采+latent；二采降 `--pass2-scale` 或拆开跑 |
| 画布空白 | 需要 bound UI Load，不是只 queue |
| Colab 奶茶 EP01 启动把付费会话拆掉 | `docs/ops/2026-10-03-colab-cup-ep01-startup.md` |

## 11. 相关文档

- 一采 vs 二采 / latent：`docs/ops/2026-09-10-render-profiles.md`
- 租卡 API 归档：`docs/ops/2026-09-09-gpu-comfy-api-archive.md`
- 端到端（偏 EP 包）：`docs/ops/2026-09-09-ep-pack-to-video-pipeline.md`
- EP03/EP04 包字段：`docs/ops/2026-09-09-ep03-ep04-yz-pack.md`
- Colab 奶茶 EP01 启动记录：`docs/ops/2026-10-03-colab-cup-ep01-startup.md`
