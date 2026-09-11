# comfyui-h3-automation

本地编排客户端：把 EP 资产包编成 YZ **MiniMax H3** 任务，经共享入口 **`vm122:8190`** 提交到租卡 ComfyUI，再拉回成片。

适合：多人共用同一台 vm122 隧道、在 WSL/Linux 上跑串行出片的团队。

**新人第一站：** [docs/HANDOFF.md](docs/HANDOFF.md)（拓扑、换卡、模式门禁、坑）

## 拓扑

```text
编排机 (WSL / Linux)
    │  HTTP  COMFY_BASE_URL
    ▼
vm122  :8190          ← 全员共用 Comfy 入口（转发跑在 vm122 上）
    │  SSH tunnel
    ▼
租卡 Comfy  127.0.0.1:8188   (H3 / CUDA)
```

```bash
export COMFY_BASE_URL=http://192.168.5.122:8190
```

| 入口 | 用途 |
|------|------|
| `http://192.168.5.122:8190` | **唯一**出片 / 浏览器 Load 地址 |
| ~~`:8188` on vm122~~ | 旧 CPU Comfy，已停用 |

换租卡、重启转发：见 HANDOFF §2 与 [`scripts/ops/`](scripts/ops/)（密码只放 vm122 `/tmp/.comfy_gpu_ssh_pass`，**勿提交**）。

## 安装

```bash
git clone https://github.com/pyhpaul/comfyui-h3-automation.git
cd comfyui-h3-automation
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

需要能访问局域网 `192.168.5.122`（或自建等价隧道后改 `COMFY_BASE_URL`）。

## 开工前硬门禁

提交队列前先确认（默认不要替别人做决定）：

1. **只一采**，还是 **一采 + 二采**（`--second-pass`）？
2. 跨 U 接力用 **`ref_video`（整片 MP4）**，还是 **`motion_latent`（AV latent）**？

说明：[docs/ops/2026-09-10-render-profiles.md](docs/ops/2026-09-10-render-profiles.md)

## 快速路径

```bash
export COMFY_BASE_URL=http://192.168.5.122:8190
comfy-orch doctor          # 应看到 CUDA / system_stats

# 1) 资产包 → job（jobs/ 不入库，每人本地生成）
python scripts/ep_pack_to_jobs.py /path/to/PACK -o jobs/ep_units --unit U01
python scripts/audit_pack_prompts.py    # EP02 wire-only：no_parent + with_parent

# 2a) 单纯一采（整片接力）
python scripts/run_ep_units_profiled.py --units U01 U02 --continuity ref_video \
  --download-dir "$HOME/Downloads/EP-compare-pass1"

# 2b) 因果验收：latent 接力 + 二采
python scripts/run_ep_units_profiled.py --units U01 U02 \
  --continuity motion_latent --second-pass \
  --download-dir "$HOME/Downloads/EP-compare-latent-mc"

# 3) 可选：导出 bound UI（浏览器 8190 Load；不入队）
python scripts/export_bound_workflow.py jobs/ep_units/<JOB> \
  --out-ui "$HOME/Downloads/<JOB>-bound-ui.json"

# 单 job
comfy-orch submit jobs/ep_units/<JOB>
comfy-orch status <job_id>
```

长 H3 任务优先用 `run_ep_units_profiled.py`；隧道抖动时按 `prompt_id` resume，勿盲目重复提交。

## 包类型与模板

| pack kind | 说明 |
|-----------|------|
| `ep02_causality` | 提示词 **wire-only**：保留包正文，只换 `<Picture N>` / `<Video 1>` |
| `h3_latent` | EP01 latent 包 |
| `seedance_upload` | EP03/EP04 上传包（可走 legacy 六段英文） |

| 模板 | 用途 |
|------|------|
| `yz_h3_ep_unit` | YZ MiniMax H3 多参考生视频（主出片） |
| `smoke_passthrough` | 连通冒烟 |
| `demo_txt` | bindings 示例 |

## 数据流

| 方向 | 方式 |
|------|------|
| 上传 | `POST {COMFY_BASE_URL}/upload/image` → 租卡 `input/` |
| 拉片 | `GET /history` + `GET /view` → 本地 `outputs/<job_id>/` |
| 对比 | 可选复制到本机 Downloads（A/B 模式目录分开） |

正常 EP 流程不需要手工 scp 素材到租卡。

## 验证

```bash
comfy-orch doctor
python -m pytest -q
python scripts/audit_pack_prompts.py
```

## 文档地图

| 路径 | 内容 |
|------|------|
| [docs/HANDOFF.md](docs/HANDOFF.md) | **交接总册**（vm122、模式、参数、坑） |
| [docs/ops/2026-09-10-render-profiles.md](docs/ops/2026-09-10-render-profiles.md) | 一采 vs latent+二采 |
| [docs/ops/2026-09-09-ep-pack-to-video-pipeline.md](docs/ops/2026-09-09-ep-pack-to-video-pipeline.md) | 端到端阶段门禁 |
| [docs/ops/2026-09-09-gpu-comfy-api-archive.md](docs/ops/2026-09-09-gpu-comfy-api-archive.md) | 租卡 / API 归档 |
| [scripts/ops/](scripts/ops/) | vm122 转发示例与重启脚本 |
| `.cursor/skills/comfy-h3-*` | Agent 分阶段 skills |

## 仓库约定

- **不要提交**密码、`.env`、租卡 SSH 密钥或真实 passfile
- **`jobs/`、`runs/`、`outputs/`** 已 gitignore（含大媒体；从资产包现场生成）
- 设计过程稿在 `docs/superpowers/`；日常以 HANDOFF + ops 为准

## License

见仓库内声明文件（若暂无则以贡献者约定为准）。
