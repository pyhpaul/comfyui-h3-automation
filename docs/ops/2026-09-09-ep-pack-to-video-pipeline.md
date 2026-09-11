# EP 资产包 → MiniMax H3 成片落地（完整流程）

**Repo:** `comfyui-h3-automation`  
**模板:** `yz_h3_ep_unit`  
**范围:** EP01 latent / **EP02 causality（wire-only）** / EP03–EP04 upload；单卡 5090 串行  
**交接：** 后续他人也走 **vm122:8190** — 见 `docs/HANDOFF.md`、`scripts/ops/`

配套 Agent Skills（可分段监督）：

| Skill | 阶段 |
|-------|------|
| `comfy-h3-ep-pipeline` | 总控 / 验收门禁 |
| `comfy-h3-env` | **环境：端口映射、doctor、上下传路径**（开跑前） |
| `comfy-h3-ep-pack-jobs` | 解析包 → job |
| `comfy-h3-pack-prompt-audit` | EP02 wire-only 提示词门禁 |
| `comfy-h3-bound-export` | 上传 + 导出 bound UI/API |
| `comfy-h3-queue-pull` | 入队、监控、拉回成片（含 profiled runner） |

路径：`.cursor/skills/<name>/SKILL.md`  
环境详表：`.cursor/skills/comfy-h3-ep-pipeline/reference-env.md`  
渲染模式：`docs/ops/2026-09-10-render-profiles.md`  
归档：`docs/ops/2026-09-09-gpu-comfy-api-archive.md`

---

## 阶段 ⓪ — 环境与端口（先于任何上传）

```text
WSL/Agent  --HTTP-->  vm122:8190  --SSH隧道-->  租卡 Comfy 127.0.0.1:8188
                         │
                         └── export COMFY_BASE_URL=http://192.168.5.122:8190
```

| 用途 | URL / 端口 | 说明 |
|------|------------|------|
| **H3 出片（编排唯一入口）** | `http://192.168.5.122:8190` | vm122 转发到 GPU `:8188` |
| GPU 本机 Comfy | `127.0.0.1:8188` | 只听 localhost，外网/局域网不能直连 |
| ~~vm122 CPU 开发 Comfy~~ | ~~`http://192.168.5.122:8188`~~ | **已停用（2026-09-10）**；勿再起 |

```bash
export COMFY_BASE_URL=http://192.168.5.122:8190
comfy-orch doctor   # 应看到 CUDA / system_stats
```

隧道掉线时在 **vm122** 重拉转发（`/tmp/comfy_ssh_forward.py`；仓库示例 `scripts/ops/`）；详见 `docs/HANDOFF.md` 与 GPU 归档。本机也可 `ssh -L 127.0.0.1:8190:127.0.0.1:8188 …` 后改用 `http://127.0.0.1:8190`。

**开跑前模式门禁（须问用户，勿默认）：**

1. 只一采 vs 一采+二采（`--second-pass`）
2. `ref_video` vs `motion_latent`  
成片对比目录按模式分开，见 `docs/ops/2026-09-10-render-profiles.md`。

### 数据上传（本地 → Comfy）

| 步骤 | 方式 | 落点 |
|------|------|------|
| 包 → job | 本地文件系统拷贝 | `jobs/ep_units/EPxx-Uyy/assets/` |
| job → 远端 | `POST /upload/image`（`ComfyClient.upload_image`，含视频/静音 wav） | Comfy 服务器 `input/`，返回文件名写入节点 |
| 浏览器看槽 | 先 upload，再 Load bound UI | 画布控件；**API `/prompt` 不改画布** |

正常 EP 流程**不需要**手工 scp 素材到租卡。

### 数据下载（Comfy → 本地）

| 步骤 | 方式 | 落点 |
|------|------|------|
| 查结果 | `GET /history/{prompt_id}` | 取 outputs 里 filename / subfolder / type |
| 拉文件 | `GET /view?...`（`collect_outputs`） | **权威：** `outputs/<job_id>/*.mp4` |
| 人工对比 | 可选复制 | `/mnt/c/Users/lxy/Downloads/<compare-dir>/`（可附 PRIOR + `prompt_h3.txt`） |

VHS 成片 `type` 常为 `temp`；文件名如 `YZ_H3_一采_00006-audio.mp4`（序号是服务器计数，不是剧集号）。

**门禁 ⓪**

- [ ] `COMFY_BASE_URL` 指向 **8190**（H3），不是 8188 CPU
- [ ] `doctor` / `/system_stats` 成功且见 GPU
- [ ] 明确 up=`/upload/image`、down=`/view` → `outputs/`

---

## 端到端示意

```text
⓪ COMFY_BASE_URL=…:8190  (tunnel OK) + 模式门禁
EP 包 (EP02 manifest/assets 或 EP03 upload-manifest + control/previz)
        │
        ▼ ① ep_pack + prompt_wire（EP02）或 h3_prompt（legacy upload）
jobs/ep_units/EPxx-Uyy/  (job.yaml, assets/, prompt_h3.txt, prompt_source.txt)
        │
        ├─► ② POST /upload/image + export_bound  ──► Downloads/*-bound-ui.json
        │
        ▼ ③ profiled runner 或 upload + bind + POST /prompt
Comfy 队列 (pending → running → history success)
        │
        ▼ ④ GET /view 拉回
outputs/<job_id>/*.mp4  +  Downloads/<compare-dir>/  (+ 可选 h3_context/*.safetensors)
```

---

## 阶段 ① — 解析资产包 → Job

**入口代码**

- `src/comfy_orch/ep_pack.py` — 按 pack kind 建 job、拷贝媒体
- `src/comfy_orch/prompt_wire.py` — **EP02 causality：保留包内文，只接线媒体标签**
- `src/comfy_orch/h3_prompt.py` — Seedance 中文包 → H3 六段英文（legacy EP03/EP04）
- `scripts/ep_pack_to_jobs.py` / `scripts/audit_pack_prompts.py`

**命令**

```bash
cd /home/linux_dev/projects/comfyui-h3-automation
source .worktrees/feat-orch/.venv/bin/activate   # 或项目 venv
# EP02 例：python scripts/ep_pack_to_jobs.py <PACK_ROOT> -o jobs/ep_units --unit U01
python scripts/ep_pack_to_jobs.py /tmp/ep02_assets/EP03 -o jobs/ep_units --unit U01
python scripts/audit_pack_prompts.py   # EP02：须 no_parent + with_parent 均过
```

> `jobs/` 已 gitignore；各人本机从包再生。

**产出**

```text
jobs/ep_units/EP03-U01/   # 或 EP02-H3-…-U0x/
  job.yaml                 # template + fields
  assets/
    …媒体…
    prompt_source.txt      # 包原文
    prompt_h3.txt          # EP02=接线后；legacy=六段英文（与 job.fields.prompt 一致）
```

**槽位契约（YZ ↔ H3 标签）**

| Job 字段 | YZ 节点 | H3 提示词标签 | 职责 |
|----------|---------|---------------|------|
| `ref_image_0` | YZ控制图 | `<Picture 1>` | 调度/站位；禁渲 UI 色块 |
| `ref_image_1..N` | YZ参考图1… | `<Picture 2..>`（+ legacy Subject） | 角色/场景身份 |
| `ref_video_0` | YZ参考视频 | `<Video 1>` | 运动/机位（`ref_video` 模式） |
| `prompt` | YZ提示词 | EP02=包文+标签；legacy=六段 | 见 `prompt_wire` / `h3_prompt` |
| `duration_seconds` | 视频时长 | — | 通常 10 |
| `aspect_ratio` / `megapixels` | 分辨率选择器 | — | 9:16；megapixels 现默认 1.0 |
| `filename_prefix` | YZ成片输出 (`VHS_VideoCombine`) | — | 默认 `{EP##}-{U##}`；远端 `{prefix}_#####-audio.mp4` |

**门禁**

- [ ] `job.yaml` 存在且 `template: yz_h3_ep_unit`
- [ ] **EP02：** audit 过；无 Windows `E:\…\assets\`；**不**强制 `subject_definitions`
- [ ] **legacy upload：** `fields.prompt` 含 `subject_definitions:` 与 `<Picture 1>`
- [ ] 无 `@char-` / 裸 `assets/` 路径残留在 prompt 中
- [ ] `prompt_source.txt` 保留包原文
- [ ] 媒体文件均存在于 job 相对路径下

---

## 阶段 ② — 导出 Bound UI（可选，给人看）

**为何需要：** `POST /prompt` **不会**改浏览器画布控件；要肉眼核对必须 Load UI JSON。

**命令**

```bash
export COMFY_BASE_URL=http://192.168.5.122:8190   # 隧道 → 租卡 Comfy
python scripts/export_bound_workflow.py jobs/ep_units/EP03-U01 \
  -o "/mnt/c/Users/lxy/Downloads/EP03-U01-yz-bound-api-h3-wiring.json" \
  --out-ui "/mnt/c/Users/lxy/Downloads/EP03-U01-yz-bound-ui-h3-wiring.json"
```

**门禁**

- [ ] UI JSON Text 含当前 `job.fields.prompt`（EP02 核因果正文+标签；legacy 可核六段）
- [ ] LoadImage / VHS 槽文件名与 job 媒体一致
- [ ] 未用图像槽为 Never 并断开（`ui_bind`）
- [ ] 人在 Comfy **Load UI**（**:8190**）核对后再决定是否 Queue

---

## 阶段 ③ — 入队执行

**入口**

- **推荐串行 A/B：** `scripts/run_ep_units_profiled.py`（`ref_video` / `motion_latent`，可选 `--second-pass`）
- `comfy-orch submit <job_dir>`（内部：`runner.submit_job`）
- 或自定义：upload → `apply_bindings` → `prune_unused_api_ref_images` → `queue_prompt` → 轮询

**环境**

- `COMFY_BASE_URL` 可达（例：`http://192.168.5.122:8190`）— **多人共用 vm122 隧道**
- 远端已装 YZ 自定义节点 + H3 `ref2va` 权重
- 单卡串行：可 **enqueue** 多个 pending，不必等空闲再提交
- 模式须已向用户确认（见文首门禁 / `.cursor/rules/h3-render-mode-gate.mdc`）

**状态**

- 本地：`runs/<job_id>/status.json`（`validating` → `running` → `done`/`failed`）
- 远端：`/queue` → `/history/{prompt_id}`（以 `status_str=success` 为准）

**注意**

- 轮询可能因隧道断连失败；任务常仍在 GPU 上 → **按 prompt_id resume**，勿盲目重复提交
- `wait_until_done` 默认超时 3600s；H3 多参考可能更久，监控脚本宜 ≥7200s 且带重试

**门禁**

- [ ] `queue_prompt` 返回 `prompt_id`，本地 status=`running`
- [ ] `/queue` 中可见 running 或 pending
- [ ] 断连后先查 queue/history，再决定 resume 或重提

---

## 阶段 ④ — 拉回成片

**入口:** `comfy_orch.artifacts.collect_outputs`（`/view`）

**落盘约定**

| 位置 | 用途 |
|------|------|
| `outputs/<job_id>/*.mp4` | 编排权威落点 |
| `C:\Users\lxy\Downloads\<compare-dir>\` | 人工对比（可附 PRIOR_*.mp4 + prompt_h3.txt） |

**门禁**

- [ ] history `success` 且 outputs 含 mp4
- [ ] 本地文件 size > 0
- [ ] status.json `state=done` 且 `outputs` 路径有效

---

## 已知对照实验（EP03-U01）

| 版本 | 提示词 | 成片（示例） | Downloads |
|------|--------|--------------|-----------|
| v1 | Seedance 原文整段 | `…_00003-audio.mp4` | `EP03-U01-comfy-outputs` / PRIOR_v1 |
| v2 | 手写 gold 六段英文 | `…_00002-audio.mp4` | `EP03-U01-h3-prompt-v2` |
| v3 | 转换器接线对齐英文 | `…_00006-audio.mp4` | `EP03-U01-h3-wiring-v3` |

观测：仅改中/英提示词形态时观感差异可能不大；控制图/previz 视觉权重可能是更大变量（后续优化项，非本流程必做）。

---

## Agent 监督用法

1. 用户说「跑 EP03-U01 / 从资产包出片」→ 读 **`comfy-h3-ep-pipeline`**
2. 总控按阶段依次 Read 并执行子 skill，每阶段过门禁再进入下一阶段
3. 任一门禁失败：停止并报告；断连用 queue-pull 的 resume 路径
4. 未经用户确认，不批量整集、不改 LoRA/steps、不强推 LLM 润色
