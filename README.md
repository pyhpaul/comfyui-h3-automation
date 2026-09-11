# comfyui-h3-automation

本地编排客户端 + 经 **vm122:8190** 隧道访问租卡 **ComfyUI MiniMax H3** 出片。

**新人请先读：** [`docs/HANDOFF.md`](docs/HANDOFF.md)

## 项目根

```text
/home/linux_dev/projects/comfyui-h3-automation
```

## 唯一出片入口

```bash
export COMFY_BASE_URL=http://192.168.5.122:8190
```

- 含义：vm122 转发 → 租卡 `127.0.0.1:8188`
- **不要**再用 `192.168.5.122:8188`（旧 CPU Comfy，已停用）
- 换租卡 / 修隧道：见 HANDOFF §2（操作在 **vm122** 上，接手人同样用 vm122）

## 安装

```bash
cd /home/linux_dev/projects/comfyui-h3-automation
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# 若已有 worktree：source .worktrees/feat-orch/.venv/bin/activate
```

## 开工前确认

1. 只跑 **一采**，还是 **一采+二采**？
2. 跨 U 接力用 **整片 `ref_video`**，还是 **`motion_latent`**？

确认前不要提交队列。说明：`docs/ops/2026-09-10-render-profiles.md`。

## 常用命令

```bash
export COMFY_BASE_URL=http://192.168.5.122:8190
comfy-orch doctor

# 资产包 → job（jobs/ 默认不入库，需自行生成）
python scripts/ep_pack_to_jobs.py /path/to/PACK -o jobs/ep_units --unit U01
python scripts/audit_pack_prompts.py

# A) 单纯一采（整片接力）
python scripts/run_ep_units_profiled.py --units U01 U02 --continuity ref_video \
  --download-dir /mnt/c/Users/lxy/Downloads/EP-compare-pass1

# B) 因果验收：latent 接力 + 二采
python scripts/run_ep_units_profiled.py --units U01 U02 \
  --continuity motion_latent --second-pass \
  --download-dir /mnt/c/Users/lxy/Downloads/EP-compare-latent-mc

# 画布可见（不入队）：导出 UI JSON，在浏览器 8190 Load
python scripts/export_bound_workflow.py jobs/ep_units/<JOB> \
  --out-ui /mnt/c/Users/lxy/Downloads/<JOB>-bound-ui.json

# 单 job 也可
comfy-orch submit jobs/ep_units/<JOB>   # 默认模板一采路径；长任务更推荐 profiled 脚本
comfy-orch status <job_id>
```

## 包类型

| kind | 说明 |
|------|------|
| `ep02_causality` | 提示词 **wire-only**（保留正文，只换媒体标签） |
| `h3_latent` | EP01 latent 包 |
| `seedance_upload` | EP03/EP04 上传包（可走旧六段转换） |

## 模板

| 模板 | 用途 |
|------|------|
| `yz_h3_ep_unit` | YZ MiniMax H3 多参考生视频（主出片） |
| `smoke_passthrough` | 连通冒烟 LoadImage→SaveImage |
| `demo_txt` | bindings 示例 |

## 数据流

| 方向 | 方式 |
|------|------|
| 上传输素材 | `POST {COMFY_BASE_URL}/upload/image` → 租卡 `input/` |
| 拉成片 | `GET /history` + `GET /view` → `outputs/<job_id>/` |
| 人工对比 | 可选复制到 `/mnt/c/Users/lxy/Downloads/…` |

## 验证

```bash
comfy-orch doctor
python -m pytest -q
python scripts/audit_pack_prompts.py
```

## 文档与 Skills

| 文档 | 内容 |
|------|------|
| `docs/HANDOFF.md` | **交接总册**（vm122 隧道、模式、坑） |
| `docs/ops/2026-09-10-render-profiles.md` | 一采 vs latent+二采 |
| `docs/ops/2026-09-09-gpu-comfy-api-archive.md` | 租卡/API 归档 |
| `docs/ops/2026-09-09-ep-pack-to-video-pipeline.md` | 端到端阶段 |
| `.cursor/skills/comfy-h3-*` | Agent 分阶段 skill |
| `scripts/ops/` | vm122 转发示例脚本 |

## 仓库约定

- **勿提交**密码、`.env`、租卡密钥
- **`jobs/`、`runs/`、`outputs/`** 已 gitignore（含素材与大视频）
- 设计稿见 `docs/superpowers/`（历史背景；以 HANDOFF + ops 为准）
