# comfyui-h3-automation

本地编排 + 远程 ComfyUI（见 `docs/superpowers/specs/`）。

## 项目根目录

```text
/home/linux_dev/projects/comfyui-h3-automation
```

开发时使用 worktree 时，以当前 checkout 为根；`comfy_orch.paths.project_root()` 解析为包所在仓库根。

## 双环境

开发与出片拆开，框架只认 `COMFY_BASE_URL`，切换环境不改业务代码。

| | VM（调流程） | 租卡（出片） |
|---|---|---|
| 用途 | 编辑工作流、导出 API JSON、验证连通 | MiniMax H3 真推理出片 |
| GPU / H3 | 可无 GPU、不装 H3 | 租 GPU，加载 H3 权重 |
| 连接 | `COMFY_BASE_URL` 指向 VM 或本机端口 | `COMFY_BASE_URL` 指向租卡（常经 SSH 隧道） |

## 环境变量

只认一个变量：

```bash
export COMFY_BASE_URL=http://127.0.0.1:8188
```

## 安装

```bash
cd /home/linux_dev/projects/comfyui-h3-automation
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## CLI

```bash
# 检查 ComfyUI 连通性
comfy-orch doctor

# 提交 job 目录（含 job.yaml），返回 job_id
comfy-orch submit path/to/job

# 查看本地 run 状态
comfy-orch status <job_id>
```

`doctor` / `submit` 需要已设置 `COMFY_BASE_URL`；`status` 只读本地 `runs/<job_id>/status.json`。

## 模板

| 模板 | 用途 |
|------|------|
| `demo_txt` | 仅提示词字段示例（调 bindings） |
| `smoke_passthrough` | VM 冒烟：`LoadImage → SaveImage`，无需 checkpoint / H3 |

## vm122 冒烟（已验证）

```bash
# 远端（SSH Host vm122 / 192.168.5.122）
# ~/ComfyUI: python main.py --listen 0.0.0.0 --port 8188 --cpu

export COMFY_BASE_URL=http://192.168.5.122:8188
comfy-orch doctor

# 示例 job：template=smoke_passthrough，fields.first_frame 指向本地 png
comfy-orch submit /path/to/job
```

## inbox 监控

```bash
# 将任务目录放入 inbox/<job-name>/（含 job.yaml）
comfy-orch watch --once          # 扫一轮后退出
comfy-orch watch --interval 5    # 持续轮询
```

成功提交的目录会移到 `inbox/.done/`；失败移到 `inbox/.failed/`。

## 可见反馈 Demo（不装扩展）

1. 浏览器打开 ComfyUI（与 `COMFY_BASE_URL` 同一实例），例如 `http://192.168.5.122:8188`。
2. 本地产出 mock 资产包并提交：

```bash
export COMFY_BASE_URL=http://192.168.5.122:8188
python scripts/mock_produce_assets.py --count 3
comfy-orch watch --once
```

3. 网页侧栏/队列应能看到任务；成片在 `outputs/<job-id>/`，状态在 `runs/<job-id>/status.json`。
4. **能看见：** 队列变化、跑完结果（视前端版本）、本地 outputs。  
   **看不见：** API 注入不会改画布上 LoadImage/提示词控件。
5. **可选细进度：** DevTools → Network → `ws` → 复制 `clientId`：

```bash
export COMFY_CLIENT_ID=<粘贴>
# 或
comfy-orch watch --once --client-id <粘贴>
```
