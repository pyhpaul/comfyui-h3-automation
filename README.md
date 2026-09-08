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
