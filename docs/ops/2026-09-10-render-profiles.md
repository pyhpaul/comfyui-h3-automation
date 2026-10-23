# EP02 渲染模式与验收流程（一采 vs latent+二采）

> **现行默认：** 只一采，场景连续用 `motion_latent`。成片进飞牛，不要 `--download-dir`。用户没明确说二采，不要加 `--second-pass`。换场或 `start_mode=independent` 不接 latent。只有明确说整片参考才用 `ref_video`。
>
> 下面的 A/B 是 EP02 当时的对照，不是现在的默认。

## 模式对照

| | **A. 整片参考（须明确要求）** | **B. 因果验收（当时的二采测试）** |
|--|-------------------------------|----------------------------|
| 开关 | `--continuity ref_video`（默认）**不要**加 `--second-pass` | `--continuity motion_latent --second-pass` |
| 跨 U 接力 | 上一 U **MP4** → `ref_video_0` + 提示词 `<Video 1>` / `父片段` | 上一 U **一采 AV latent** → Motion Context Load（**无** MP4 parent） |
| 单 U 采样 | 仅一采 `SamplerCustomAdvanced` → `*-audio.mp4` | 一采 → Save latent →（可选）Upscale 1.5 → 二采 → `*-pass1` + `*-pass2` |
| 二采 | 无 | 有；二采用**独立 guider**（不复用 Motion Context 条件，避免升采样 shape mismatch） |
| 典型目录 | `Downloads\EP02-H3-causality-v21-rewire\` | `Downloads\EP02-H3-causality-v21-latent-mc\` |
| 成片命名 | `EP02-U0x_XXXXX-audio.mp4` | `EP02-U0x-pass1_*.mp4`、`EP02-U0x-pass2_*.mp4` |
| Latent | 通常不落盘 | `h3_context/ep02_u0x_0000N.safetensors`（`video`+`audio`，format `h3_motion_context_av_v1`） |

代码入口：

- 脚本：`scripts/run_ep_units_profiled.py`
- 叠加图：`comfy_orch.render_profile.RenderProfile` / `apply_render_profile`
- 提示词审核：仍用 pack wire-only；`motion_latent` 模式**不**注入 `<Video 1>`

## 命令

现行：

```bash
export COMFY_BASE_URL=http://192.168.50.106:8190
export PYTHONPATH=src
cd /home/linux_dev/projects/comfyui-h3-automation
source .worktrees/feat-orch/.venv/bin/activate

python scripts/run_ep_units_profiled.py --units U01 U02 \
  --continuity motion_latent \
  --feiniu-batch '<批次>'
```

下面是 EP02 当时的对照，不要照抄 `--download-dir`：

```bash
# A — 整片参考（须明确要求）
python scripts/run_ep_units_profiled.py --units U01 U02 --continuity ref_video \
  --download-dir /mnt/c/Users/lxy/Downloads/EP02-H3-causality-v21-rewire

# B — 因果验收：latent 接力 + 二采
python scripts/run_ep_units_profiled.py --units U01 U02 \
  --continuity motion_latent --second-pass \
  --download-dir /mnt/c/Users/lxy/Downloads/EP02-H3-causality-v21-latent-mc

# 从已有 latent 续跑（例：只重跑 U02）
python scripts/run_ep_units_profiled.py --units U02 \
  --continuity motion_latent --second-pass \
  --parent-latent h3_context/ep02_u01_00001.safetensors \
  --download-dir /mnt/c/Users/lxy/Downloads/EP02-H3-causality-v21-latent-mc
```

提交前审核：`python scripts/audit_pack_prompts.py`（no_parent + with_parent 双路径；`motion_latent` 串行仍以现场 audit 为准）。

## 本次 B 模式实测记录（2026-09-10）

| Unit | 结果 | 要点 |
|------|------|------|
| U01 | 成功（一次生成） | prompt `85e29243…`；`pass1`+`pass2`+`ep02_u01_00001.safetensors` **同一次工作流新跑**，非复用 rewire 旧片 |
| U02 第一次 | 一采/latent 成功，二采失败 | prompt `66f4009d…`；二采复用 Motion Context guider → shape mismatch |
| U02 重试 | 成功 | prompt `b56b8434…`；二采改独立 guider；parent=`h3_context/ep02_u01_00001.safetensors` |

产物根目录：`/mnt/c/Users/lxy/Downloads/EP02-H3-causality-v21-latent-mc/`

- U01：`EP02-U01-pass1_00001-audio.mp4`、`EP02-U01-pass2_00001-audio.mp4`、`ep02_u01_00001.safetensors`
- U02：`EP02-U02-pass1_00002-audio.mp4`、`EP02-U02-pass2_00001-audio.mp4`、`ep02_u02_00002.safetensors`（另有失败轮留下的 `pass1_00001`）

### 易混点（写给后续自己）

1. **`pass1` ≠ 上次一采旧文件**：B 模式下 pass1/pass2 都是该次图新采样；与 `…-rewire\` 下无 `-pass1` 后缀的片子 hash 不同。
2. **跨 U 应用一采 latent，不是二采 latent**（分辨率一致；二采只做观感）。
3. **A/B 不要共用同一 download 目录**，以免把「仅一采」和「pass1/pass2/latent」混在一起验收。

## 相关

- Pack 提示词审核：`.cursor/skills/comfy-h3-pack-prompt-audit/SKILL.md`
- 简短 flags 备忘：本文件前身要点亦见同目录早期草稿；**以本文件为准**
