# Comfy UI Visible Feedback (No Extension) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让可选的浏览器 `client_id` 传入 `/prompt`，固化 mock→inbox→watch 演示路径，并在 README 写清「开着 Comfy 网页能看见什么」。

**Architecture:** 在现有 `ComfyClient`（已带随机 `client_id`）上增加显式覆盖；经 `submit_job` / inbox / CLI / `COMFY_CLIENT_ID` 透传。不装扩展、不改画布同步。

**Tech Stack:** 现有 Python 包 `comfy_orch`、typer、pytest-httpx；远端仍为 `COMFY_BASE_URL`。

**Spec:** `docs/superpowers/specs/2026-09-08-comfy-ui-visible-feedback-no-extension-design.md`

**Project root:** `/home/linux_dev/projects/comfyui-h3-automation`

---

## File structure

| Path | Responsibility |
|------|----------------|
| `src/comfy_orch/client.py` | `ComfyClient(base_url, client_id=None)`；未传则随机 UUID（保持现状） |
| `src/comfy_orch/runner.py` | `submit_job(..., client_id=None)` 传给 `ComfyClient` |
| `src/comfy_orch/inbox.py` | `process_inbox_once` / `watch_inbox` 透传 `client_id` |
| `src/comfy_orch/cli.py` | `--client-id` + 读 `COMFY_CLIENT_ID`；`submit`/`watch`/`doctor` 共用解析 |
| `tests/test_client.py` | 断言自定义 `client_id` 出现在 POST `/prompt` body |
| `tests/test_runner_mock.py` | 若有构造 Client 处，覆盖透传（或 inbox 单测） |
| `scripts/mock_produce_assets.py` | 已存在则纳入版本库；按需微调 |
| `README.md` | 「可见反馈 Demo」小节 |
| `.env.example` | 增加 `COMFY_CLIENT_ID=` 注释行 |

---

### Task 1: Client 支持显式 `client_id`

**Files:**
- Modify: `src/comfy_orch/client.py`
- Modify: `tests/test_client.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_client.py` 增加：

```python
def test_queue_prompt_uses_explicit_client_id(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}/prompt",
        method="POST",
        json={"prompt_id": "pid-x", "number": 1, "node_errors": {}},
    )
    client = ComfyClient(BASE, client_id="browser-ws-id-1")
    assert client.client_id == "browser-ws-id-1"
    assert client.queue_prompt({"1": {}}) == "pid-x"
    req = httpx_mock.get_request()
    body = json.loads(req.content.decode())
    assert body["client_id"] == "browser-ws-id-1"
    assert body["prompt"] == {"1": {}}
```

（文件顶部确保 `import json`。）

- [ ] **Step 2: 跑测试确认失败或需改实现**

Run: `cd /home/linux_dev/projects/comfyui-h3-automation && source .worktrees/feat-orch/.venv/bin/activate && pytest tests/test_client.py::test_queue_prompt_uses_explicit_client_id -v`

Expected: 若构造器尚不接受 `client_id` kwarg → TypeError/FAIL；再改实现。

- [ ] **Step 3: 改 `ComfyClient.__init__`**

```python
def __init__(self, base_url: str, timeout: float = 60.0, client_id: str | None = None):
    self.base_url = base_url.rstrip("/")
    self._client = httpx.Client(base_url=self.base_url, timeout=timeout)
    self.client_id = client_id if client_id else str(uuid.uuid4())
```

`queue_prompt` 保持继续发送 `self.client_id`（已有逻辑可不动）。

- [ ] **Step 4: 跑相关测试通过**

Run: `pytest tests/test_client.py -q`  
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/comfy_orch/client.py tests/test_client.py
git commit -m "feat: allow explicit Comfy client_id for UI progress alignment"
```

---

### Task 2: Runner / inbox / CLI 透传

**Files:**
- Modify: `src/comfy_orch/runner.py`
- Modify: `src/comfy_orch/inbox.py`
- Modify: `src/comfy_orch/cli.py`
- Modify: `tests/test_inbox_and_retry.py`（或新建断言）

- [ ] **Step 1: 写失败测试（inbox 透传）**

在 `tests/test_inbox_and_retry.py` 增加：

```python
def test_process_inbox_passes_client_id(tmp_path: Path):
    inbox = tmp_path / "inbox"
    job = inbox / "j1"
    job.mkdir(parents=True)
    (job / "job.yaml").write_text("template: x\nfields: {}\n", encoding="utf-8")
    seen: dict = {}

    def fake_submit(job_dir, *, base_url, root, client_id=None):
        seen["client_id"] = client_id
        return "abc123"

    from comfy_orch.inbox import process_inbox_once

    process_inbox_once(
        inbox,
        base_url="http://comfy.test",
        root=tmp_path,
        submit=fake_submit,
        client_id="from-cli",
    )
    assert seen["client_id"] == "from-cli"
```

- [ ] **Step 2: 跑测确认失败**

Run: `pytest tests/test_inbox_and_retry.py::test_process_inbox_passes_client_id -v`  
Expected: FAIL（`process_inbox_once` 尚无 `client_id`）

- [ ] **Step 3: 改 runner**

`submit_job` 签名改为：

```python
def submit_job(
    job_dir: Path,
    *,
    base_url: str,
    root: Path,
    client_id: str | None = None,
) -> str:
```

创建客户端处：

```python
client = ComfyClient(base_url, client_id=client_id)
```

- [ ] **Step 4: 改 inbox**

`process_inbox_once` / `watch_inbox` 增加 `client_id: str | None = None`，调用：

```python
job_id = submit(job_dir, base_url=base_url, root=root, client_id=client_id)
```

（`submit` 默认仍为 `submit_job`；测试用 fake 需接受同关键字。）

- [ ] **Step 5: 改 CLI**

在 `cli.py` 增加：

```python
def _client_id(explicit: str | None) -> str | None:
    if explicit and explicit.strip():
        return explicit.strip()
    env = os.environ.get("COMFY_CLIENT_ID", "").strip()
    return env or None
```

`submit`：

```python
def submit(
    job_dir: Path,
    client_id: str | None = typer.Option(None, "--client-id", help="Browser WS clientId"),
) -> None:
    ...
    job_id = submit_job(
        job_dir,
        base_url=_base_url(),
        root=project_root(),
        client_id=_client_id(client_id),
    )
```

`watch` 同样增加 `--client-id`，传入 `process_inbox_once` / `watch_inbox`。

- [ ] **Step 6: 全量单测**

Run: `pytest -q`  
Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
git add src/comfy_orch/runner.py src/comfy_orch/inbox.py src/comfy_orch/cli.py tests/test_inbox_and_retry.py
git commit -m "feat: plumb COMFY_CLIENT_ID and --client-id through submit/watch"
```

---

### Task 3: Demo 脚本入库 + README / .env.example

**Files:**
- Add: `scripts/mock_produce_assets.py`（若仍为 untracked）
- Modify: `README.md`
- Modify: `.env.example`

- [ ] **Step 1: 确认脚本可运行**

Run: `python scripts/mock_produce_assets.py --help`  
Expected: 打印用法，exit 0

- [ ] **Step 2: 更新 `.env.example`**

```bash
COMFY_BASE_URL=http://127.0.0.1:8188
# Optional: paste clientId from Comfy UI DevTools → Network → ws ?clientId=
# COMFY_CLIENT_ID=
```

- [ ] **Step 3: README 增加「可见反馈 Demo」**

在 README 合适位置追加（中英可混，与现有中文风格一致）：

```markdown
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
```

- [ ] **Step 4: Commit**

```bash
git add scripts/mock_produce_assets.py README.md .env.example
git commit -m "docs: add visible-feedback demo path and optional client id"
```

---

### Task 4: vm122 冒烟（手工）

**Files:** 无代码（验证）

- [ ] **Step 1: doctor**

```bash
export COMFY_BASE_URL=http://192.168.5.122:8188
comfy-orch doctor
```

Expected: 打印 system_stats JSON，非报错退出。

- [ ] **Step 2: mock + watch**

```bash
rm -rf inbox/mock_job_* 2>/dev/null; python scripts/mock_produce_assets.py --count 2
comfy-orch watch --once
```

Expected: `OK mock_job_... -> <job_id>`；`outputs/<job_id>/` 有 png；`runs/<job_id>/status.json` 为 `done`。

- [ ] **Step 3: 记录**

若 doctor/Comfy 不可达：在提交说明或 PR 描述写明跳过原因，不把冒烟失败当成代码回归（单测已绿即可合入）。

- [ ] **Step 4: 无代码则无需 commit；若有修复再单独 commit**

---

## Spec coverage check

| Spec 项 | Task |
|---------|------|
| 可选 client_id CLI/环境变量 | Task 1–2 |
| mock → inbox → watch 固化 | Task 3（脚本）+ Task 4 |
| README 可见/不可见说明 | Task 3 |
| 单测 queue_prompt body | Task 1 |
| vm122 冒烟 | Task 4 |
| 不做扩展/画布回填/自建大屏 | 无任务（刻意不做） |

## Placeholder scan

无 TBD/TODO；步骤含具体代码与命令。
