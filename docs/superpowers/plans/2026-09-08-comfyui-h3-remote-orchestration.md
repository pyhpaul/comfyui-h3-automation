# ComfyUI 远程编排框架 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在本地用 CLI 提交 job 目录，经完整性校验与 bindings 注入后调用远程 ComfyUI API，并把成片拉到本地 `outputs/`。

**Architecture:** 精简自研包 `comfy_orch`：Manifest 门禁 → Binder（Title 优先）→ Comfy Client（HTTP + 可选 WS）→ Job Runner 状态机；只认 `COMFY_BASE_URL`。第一期串行、CLI 优先；不含开关机/隧道/inbox。

**Tech Stack:** Python 3.11+、httpx、PyYAML、typer、pytest；WebSocket 用 `httpx` 不可时用标准库或 `websocket-client` 做完成等待（优先轮询 `/history` 以保证测试简单，WS 作可选加速）。

**Project root:** `/home/linux_dev/projects/comfyui-h3-automation`（勿在 `/home/linux_dev` 根目录执行）

**Spec:** `docs/superpowers/specs/2026-09-08-comfyui-h3-remote-orchestration-design.md`

---

## File structure

| Path | Responsibility |
|------|----------------|
| `pyproject.toml` | 包元数据、依赖、pytest、console script |
| `src/comfy_orch/__init__.py` | 版本号 |
| `src/comfy_orch/paths.py` | 解析模板目录、runs、outputs 根路径 |
| `src/comfy_orch/errors.py` | 领域异常（ValidationError、ConnectionError、…） |
| `src/comfy_orch/manifest.py` | 读 `job.yaml` + schema 校验 |
| `src/comfy_orch/binder.py` | bindings → 改 API workflow dict |
| `src/comfy_orch/client.py` | ComfyUI HTTP 客户端 |
| `src/comfy_orch/artifacts.py` | 下载落盘 |
| `src/comfy_orch/status.py` | `runs/<job-id>/status.json` 读写 |
| `src/comfy_orch/runner.py` | 编排状态机 |
| `src/comfy_orch/cli.py` | typer：doctor / submit / status |
| `templates/demo_txt/` | 最小示例模板（假节点图，供 mock 与文档） |
| `tests/fixtures/` | 夹具 job、workflow、bindings |
| `tests/test_manifest.py` | |
| `tests/test_binder.py` | |
| `tests/test_client.py` | |
| `tests/test_runner_mock.py` | 假 ComfyUI 集成 |
| `tests/mock_comfy_server.py` | 测试用 aiohttp/httpx ASGI 或 threading HTTPServer |
| `README.md` | 双环境说明 + CLI 用法 |
| `.env.example` | `COMFY_BASE_URL=` |
| `.gitignore` | `.venv`、`runs/`、`outputs/`、`.superpowers/` |

---

### Task 1: 脚手架

**Files:**
- Create: `pyproject.toml`
- Create: `src/comfy_orch/__init__.py`
- Create: `src/comfy_orch/errors.py`
- Create: `src/comfy_orch/paths.py`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `README.md`（先写项目根与安装三行）

- [ ] **Step 1: 写 `pyproject.toml`**

```toml
[project]
name = "comfy-orch"
version = "0.1.0"
description = "Local orchestration client for remote ComfyUI"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
  "httpx>=0.27",
  "pyyaml>=6.0",
  "typer>=0.12",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-httpx>=0.30"]

[project.scripts]
comfy-orch = "comfy_orch.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/comfy_orch"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 2: 写基础模块**

`src/comfy_orch/__init__.py`:
```python
__version__ = "0.1.0"
```

`src/comfy_orch/errors.py`:
```python
class ComfyOrchError(Exception):
    """Base error."""


class ValidationError(ComfyOrchError):
    pass


class ConnectionFailed(ComfyOrchError):
    pass


class QueueRejected(ComfyOrchError):
    pass


class ExecutionFailed(ComfyOrchError):
    pass


class CollectFailed(ComfyOrchError):
    pass
```

`src/comfy_orch/paths.py`:
```python
from pathlib import Path

def project_root() -> Path:
    # package at src/comfy_orch → parents[2] is repo root when editable
    return Path(__file__).resolve().parents[2]

def templates_dir(root: Path | None = None) -> Path:
    return (root or project_root()) / "templates"

def runs_dir(root: Path | None = None) -> Path:
    return (root or project_root()) / "runs"

def outputs_dir(root: Path | None = None) -> Path:
    return (root or project_root()) / "outputs"
```

`.gitignore`:
```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
runs/
outputs/
.env
.superpowers/
dist/
*.egg-info/
```

`.env.example`:
```
COMFY_BASE_URL=http://127.0.0.1:8188
```

`README.md` 开头：
```markdown
# comfyui-h3-automation

本地编排 + 远程 ComfyUI（见 `docs/superpowers/specs/`）。

```bash
cd /home/linux_dev/projects/comfyui-h3-automation
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```
```

- [ ] **Step 3: 安装并确认 import**

Run:
```bash
cd /home/linux_dev/projects/comfyui-h3-automation
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -c "import comfy_orch; print(comfy_orch.__version__)"
```
Expected: `0.1.0`

- [ ] **Step 4: Commit（若已 `git init` 且用户要求提交）**

```bash
git add pyproject.toml src/comfy_orch .gitignore .env.example README.md
git commit -m "$(cat <<'EOF'
chore: scaffold comfy-orch package

EOF
)"
```

---

### Task 2: Manifest 校验

**Files:**
- Create: `src/comfy_orch/manifest.py`
- Create: `tests/fixtures/jobs/ok_job/job.yaml`
- Create: `tests/fixtures/jobs/ok_job/assets/ref.png`（任意小 PNG，或测试里临时写字节）
- Create: `tests/fixtures/templates/demo/manifest.schema.yaml`
- Create: `tests/test_manifest.py`

- [ ] **Step 1: 写失败测试**

`tests/fixtures/templates/demo/manifest.schema.yaml`:
```yaml
required_fields:
  - prompt
required_files:
  - first_frame
```

`tests/test_manifest.py`:
```python
from pathlib import Path
import pytest
from comfy_orch.manifest import load_and_validate_job
from comfy_orch.errors import ValidationError

FIXTURES = Path(__file__).parent / "fixtures"

def test_missing_file_raises(tmp_path: Path):
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "job.yaml").write_text(
        "template: demo\nfields:\n  prompt: hello\n  first_frame: assets/missing.png\n",
        encoding="utf-8",
    )
    schema = FIXTURES / "templates" / "demo" / "manifest.schema.yaml"
    with pytest.raises(ValidationError, match="first_frame"):
        load_and_validate_job(job_dir, schema_path=schema)

def test_ok_job_returns_payload(tmp_path: Path):
    job_dir = tmp_path / "job"
    (job_dir / "assets").mkdir(parents=True)
    (job_dir / "assets" / "ref.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (job_dir / "job.yaml").write_text(
        "template: demo\nfields:\n  prompt: hello\n  first_frame: assets/ref.png\n",
        encoding="utf-8",
    )
    schema = FIXTURES / "templates" / "demo" / "manifest.schema.yaml"
    job = load_and_validate_job(job_dir, schema_path=schema)
    assert job.template == "demo"
    assert job.fields["prompt"] == "hello"
    assert job.resolve_path("first_frame").is_file()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /home/linux_dev/projects/comfyui-h3-automation && source .venv/bin/activate && pytest tests/test_manifest.py -v`  
Expected: FAIL（`load_and_validate_job` 未定义）

- [ ] **Step 3: 最小实现**

`src/comfy_orch/manifest.py`:
```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from comfy_orch.errors import ValidationError


@dataclass
class JobSpec:
    template: str
    fields: dict[str, Any]
    job_dir: Path

    def resolve_path(self, field_name: str) -> Path:
        rel = self.fields[field_name]
        return (self.job_dir / rel).resolve()


def load_and_validate_job(job_dir: Path, schema_path: Path) -> JobSpec:
    job_dir = job_dir.resolve()
    job_file = job_dir / "job.yaml"
    if not job_file.is_file():
        raise ValidationError(f"missing job.yaml in {job_dir}")

    raw = yaml.safe_load(job_file.read_text(encoding="utf-8")) or {}
    template = raw.get("template")
    fields = raw.get("fields") or {}
    if not template:
        raise ValidationError("job.yaml missing template")

    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8")) or {}
    for key in schema.get("required_fields") or []:
        if key not in fields or fields[key] in (None, ""):
            raise ValidationError(f"missing required field: {key}")
    for key in schema.get("required_files") or []:
        if key not in fields:
            raise ValidationError(f"missing required file field: {key}")
        path = (job_dir / str(fields[key])).resolve()
        if not path.is_file():
            raise ValidationError(f"missing file for {key}: {fields[key]}")

    return JobSpec(template=str(template), fields=dict(fields), job_dir=job_dir)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_manifest.py -v`  
Expected: PASS

- [ ] **Step 5: Commit（若用户要求）**

```bash
git add src/comfy_orch/manifest.py tests/
git commit -m "$(cat <<'EOF'
feat: validate job manifest against template schema

EOF
)"
```

---

### Task 3: Binder（Title 优先，ID 回退）

**Files:**
- Create: `src/comfy_orch/binder.py`
- Create: `tests/fixtures/templates/demo/workflow_api.json`
- Create: `tests/fixtures/templates/demo/bindings.yaml`
- Create: `tests/test_binder.py`

- [ ] **Step 1: 写失败测试与夹具**

`tests/fixtures/templates/demo/workflow_api.json`:
```json
{
  "6": {
    "class_type": "CLIPTextEncode",
    "_meta": {"title": "正向提示词"},
    "inputs": {"text": "OLD", "clip": ["4", 1]}
  },
  "10": {
    "class_type": "LoadImage",
    "_meta": {"title": "首帧"},
    "inputs": {"image": "old.png"}
  }
}
```

`tests/fixtures/templates/demo/bindings.yaml`:
```yaml
bindings:
  - field: prompt
    node_title: 正向提示词
    input: text
  - field: first_frame
    node_title: 首帧
    input: image
    media: true
```

`tests/test_binder.py`:
```python
import json
from pathlib import Path
from comfy_orch.binder import apply_bindings

FIXTURES = Path(__file__).parent / "fixtures" / "templates" / "demo"

def test_apply_by_title():
    workflow = json.loads((FIXTURES / "workflow_api.json").read_text(encoding="utf-8"))
    bindings = (FIXTURES / "bindings.yaml").read_text(encoding="utf-8")
    out = apply_bindings(
        workflow,
        bindings_yaml=bindings,
        values={"prompt": "NEW", "first_frame": "uploaded.png"},
    )
    assert out["6"]["inputs"]["text"] == "NEW"
    assert out["10"]["inputs"]["image"] == "uploaded.png"
```

- [ ] **Step 2: 跑测确认失败**

Run: `pytest tests/test_binder.py -v`  
Expected: FAIL

- [ ] **Step 3: 实现 binder**

`src/comfy_orch/binder.py`:
```python
from __future__ import annotations
import copy
from typing import Any

import yaml

from comfy_orch.errors import ValidationError


def apply_bindings(
    workflow: dict[str, Any],
    *,
    bindings_yaml: str,
    values: dict[str, Any],
) -> dict[str, Any]:
    cfg = yaml.safe_load(bindings_yaml) or {}
    out = copy.deepcopy(workflow)
    for item in cfg.get("bindings") or []:
        field = item["field"]
        if field not in values:
            continue
        node_id = _resolve_node_id(out, item)
        input_name = item["input"]
        out[node_id]["inputs"][input_name] = values[field]
    return out


def list_media_fields(bindings_yaml: str) -> list[str]:
    cfg = yaml.safe_load(bindings_yaml) or {}
    return [i["field"] for i in (cfg.get("bindings") or []) if i.get("media")]


def _resolve_node_id(workflow: dict[str, Any], item: dict[str, Any]) -> str:
    if title := item.get("node_title"):
        for nid, node in workflow.items():
            meta = node.get("_meta") or {}
            if meta.get("title") == title:
                return str(nid)
        raise ValidationError(f"node title not found: {title}")
    if nid := item.get("node_id"):
        if str(nid) not in workflow:
            raise ValidationError(f"node id not found: {nid}")
        return str(nid)
    raise ValidationError("binding needs node_title or node_id")
```

- [ ] **Step 4: 跑测确认通过**

Run: `pytest tests/test_binder.py -v`  
Expected: PASS

- [ ] **Step 5: Commit（若用户要求）**

```bash
git add src/comfy_orch/binder.py tests/
git commit -m "$(cat <<'EOF'
feat: bind job fields into ComfyUI API workflow JSON

EOF
)"
```

---

### Task 4: Comfy Client

**Files:**
- Create: `src/comfy_orch/client.py`
- Create: `tests/test_client.py`

- [ ] **Step 1: 用 pytest-httpx 写失败测试**

```python
import httpx
import pytest
from pytest_httpx import HTTPXMock
from comfy_orch.client import ComfyClient

def test_system_stats_ok(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url="http://comfy.test/system_stats", json={"system": {}})
    c = ComfyClient("http://comfy.test")
    assert c.system_stats()["system"] == {}

def test_upload_image(httpx_mock: HTTPXMock, tmp_path):
    path = tmp_path / "a.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    httpx_mock.add_response(
        url="http://comfy.test/upload/image",
        method="POST",
        json={"name": "a.png", "subfolder": "", "type": "input"},
    )
    c = ComfyClient("http://comfy.test")
    assert c.upload_image(path) == "a.png"

def test_queue_prompt(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="http://comfy.test/prompt",
        method="POST",
        json={"prompt_id": "pid-1", "number": 1},
    )
    c = ComfyClient("http://comfy.test")
    assert c.queue_prompt({"1": {}}) == "pid-1"

def test_wait_history(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="http://comfy.test/history/pid-1",
        json={"pid-1": {"outputs": {"9": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}}}},
    )
    c = ComfyClient("http://comfy.test")
    hist = c.wait_until_done("pid-1", poll_interval=0.01, timeout=1.0)
    assert "outputs" in hist

def test_download_view(httpx_mock: HTTPXMock, tmp_path):
    httpx_mock.add_response(
        url="http://comfy.test/view",
        json=None,
        content=b"VIDEO",
    )
    # pytest-httpx matches query; use callback if needed
    c = ComfyClient("http://comfy.test")
    dest = tmp_path / "out.bin"
    # implement download_file(filename, dest, subfolder="", type_="output")
    c.download_view(filename="out.png", dest=dest)
    assert dest.read_bytes() == b"VIDEO"
```

若 `view` URL 带 query 导致 mock 难匹配，在实现里用 `httpx.Client.get` 并在测试里用 `url__startswith` 或自定义 matcher（按 pytest-httpx 文档调整）。

- [ ] **Step 2: 跑测确认失败**

Run: `pytest tests/test_client.py -v`  
Expected: FAIL

- [ ] **Step 3: 实现 client（第一期完成等待用轮询，不做 WS）**

`src/comfy_orch/client.py`:
```python
from __future__ import annotations
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from comfy_orch.errors import ConnectionFailed, QueueRejected, ExecutionFailed, CollectFailed


class ComfyClient:
    def __init__(self, base_url: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)
        self.client_id = str(uuid.uuid4())

    def close(self) -> None:
        self._client.close()

    def system_stats(self) -> dict[str, Any]:
        try:
            r = self._client.get("/system_stats")
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise ConnectionFailed(str(e)) from e

    def upload_image(self, path: Path, overwrite: bool = True) -> str:
        with path.open("rb") as f:
            r = self._client.post(
                "/upload/image",
                files={"image": (path.name, f, "application/octet-stream")},
                data={"overwrite": "true" if overwrite else "false"},
            )
        r.raise_for_status()
        return r.json()["name"]

    def queue_prompt(self, workflow: dict[str, Any]) -> str:
        r = self._client.post(
            "/prompt",
            json={"prompt": workflow, "client_id": self.client_id},
        )
        data = r.json()
        if r.status_code >= 400 or data.get("node_errors"):
            raise QueueRejected(str(data))
        return data["prompt_id"]

    def wait_until_done(
        self,
        prompt_id: str,
        *,
        poll_interval: float = 1.0,
        timeout: float = 3600.0,
    ) -> dict[str, Any]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = self._client.get(f"/history/{prompt_id}")
            r.raise_for_status()
            data = r.json()
            if prompt_id in data:
                entry = data[prompt_id]
                if entry.get("status", {}).get("status_str") == "error":
                    raise ExecutionFailed(str(entry.get("status")))
                return entry
            time.sleep(poll_interval)
        raise ExecutionFailed(f"timeout waiting for {prompt_id}")

    def download_view(
        self,
        *,
        filename: str,
        dest: Path,
        subfolder: str = "",
        type_: str = "output",
    ) -> Path:
        try:
            r = self._client.get(
                "/view",
                params={"filename": filename, "subfolder": subfolder, "type": type_},
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise CollectFailed(str(e)) from e
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        return dest
```

注意：真实 ComfyUI history 在完成后即出现条目；测试 mock 直接返回完整 history。若真实环境 `status` 字段形态不同，以「prompt_id 出现在 history」为完成条件即可（与官方脚本一致）。

- [ ] **Step 4: 跑测确认通过**（按需微调 httpx_mock URL）

Run: `pytest tests/test_client.py -v`  
Expected: PASS

- [ ] **Step 5: Commit（若用户要求）**

```bash
git add src/comfy_orch/client.py tests/test_client.py
git commit -m "$(cat <<'EOF'
feat: add ComfyUI HTTP client

EOF
)"
```

---

### Task 5: Status + Artifacts

**Files:**
- Create: `src/comfy_orch/status.py`
- Create: `src/comfy_orch/artifacts.py`
- Create: `tests/test_status.py`

- [ ] **Step 1: 测试 status 读写**

```python
from comfy_orch.status import JobStatus, write_status, read_status

def test_status_roundtrip(tmp_path):
    p = tmp_path / "runs" / "j1" / "status.json"
    st = JobStatus(job_id="j1", state="pending", prompt_id=None, message="", outputs=[])
    write_status(p, st)
    got = read_status(p)
    assert got.state == "pending"
    assert got.job_id == "j1"
```

- [ ] **Step 2: 跑测失败 → 实现**

`src/comfy_orch/status.py`:
```python
from __future__ import annotations
from dataclasses import dataclass, asdict, field
from pathlib import Path
import json
from typing import Any


@dataclass
class JobStatus:
    job_id: str
    state: str
    prompt_id: str | None = None
    message: str = ""
    outputs: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


def write_status(path: Path, status: JobStatus) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(status), ensure_ascii=False, indent=2), encoding="utf-8")


def read_status(path: Path) -> JobStatus:
    data = json.loads(path.read_text(encoding="utf-8"))
    return JobStatus(**{k: data[k] for k in ("job_id", "state", "prompt_id", "message", "outputs", "extra") if k in data or k in ("job_id", "state")})
```

修正 `read_status` 使缺省字段安全：

```python
def read_status(path: Path) -> JobStatus:
    data = json.loads(path.read_text(encoding="utf-8"))
    return JobStatus(
        job_id=data["job_id"],
        state=data["state"],
        prompt_id=data.get("prompt_id"),
        message=data.get("message", ""),
        outputs=list(data.get("outputs") or []),
        extra=dict(data.get("extra") or {}),
    )
```

`src/comfy_orch/artifacts.py`:
```python
from __future__ import annotations
from pathlib import Path
from typing import Any
from comfy_orch.client import ComfyClient

def collect_outputs(client: ComfyClient, history_entry: dict[str, Any], dest_dir: Path) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    outputs = history_entry.get("outputs") or {}
    for _node, payload in outputs.items():
        for key in ("images", "gifs", "videos"):
            for item in payload.get(key) or []:
                filename = item["filename"]
                dest = dest_dir / filename
                client.download_view(
                    filename=filename,
                    dest=dest,
                    subfolder=item.get("subfolder") or "",
                    type_=item.get("type") or "output",
                )
                saved.append(dest)
    return saved
```

- [ ] **Step 3: 跑通 status 测试**

Run: `pytest tests/test_status.py -v`  
Expected: PASS

- [ ] **Step 4: Commit（若用户要求）**

---

### Task 6: Job Runner

**Files:**
- Create: `src/comfy_orch/runner.py`
- Create: `tests/test_runner_mock.py`
- Create: `tests/mock_comfy_server.py`（或纯 pytest-httpx 串起整链）

- [ ] **Step 1: 用 httpx_mock 写一条端到端 Runner 测试**

覆盖：缺图不调远端；齐备时 upload → prompt → history → 落盘 → status done。

伪代码要点（写完整可运行测试）：

```python
def test_runner_happy_path(httpx_mock, tmp_path, monkeypatch):
    # 准备 repo 布局：templates/demo/{workflow,bindings,schema} + job_dir
    # mock system_stats, upload, prompt, history, view
    # root = tmp_path 作为 project root
    from comfy_orch.runner import submit_job
    job_id = submit_job(job_dir, base_url="http://comfy.test", root=tmp_path)
    st = read_status(tmp_path / "runs" / job_id / "status.json")
    assert st.state == "done"
    assert st.outputs
```

- [ ] **Step 2: 跑测失败 → 实现 `submit_job`**

`src/comfy_orch/runner.py` 流程（与 spec 一致）：

1. 生成 `job_id`（`uuid4` hex 短码）  
2. 写 status `validating`  
3. `schema = templates/<template>/manifest.schema.yaml` → `load_and_validate_job`  
4. `ComfyClient.system_stats()`；失败 → `connecting`/`failed`  
5. 读 bindings，对 media 字段 `upload_image`，把 values 里对应项换成远端文件名  
6. `apply_bindings` → `queue_prompt`  
7. `wait_until_done`  
8. `collect_outputs` 到 `outputs/<job_id>/`  
9. status `done`  

串行：模块级 `threading.Lock`（同一进程内）。

- [ ] **Step 3: 跑测通过**

Run: `pytest tests/test_runner_mock.py -v`  
Expected: PASS

- [ ] **Step 4: Commit（若用户要求）**

```bash
git commit -m "$(cat <<'EOF'
feat: add job runner orchestration

EOF
)"
```

---

### Task 7: CLI

**Files:**
- Create: `src/comfy_orch/cli.py`
- Modify: `README.md`

- [ ] **Step 1: 实现 typer app**

```python
import os
from pathlib import Path
import typer
from comfy_orch.client import ComfyClient
from comfy_orch.runner import submit_job
from comfy_orch.status import read_status
from comfy_orch.paths import runs_dir, project_root
from comfy_orch.errors import ComfyOrchError

app = typer.Typer(help="Remote ComfyUI orchestration")

def _base_url() -> str:
    url = os.environ.get("COMFY_BASE_URL", "").strip()
    if not url:
        raise typer.BadParameter("set COMFY_BASE_URL")
    return url

@app.command()
def doctor() -> None:
    c = ComfyClient(_base_url())
    try:
        stats = c.system_stats()
    finally:
        c.close()
    typer.echo(stats)

@app.command()
def submit(job_dir: Path) -> None:
    try:
        job_id = submit_job(job_dir, base_url=_base_url(), root=project_root())
    except ComfyOrchError as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1) from e
    typer.echo(job_id)

@app.command()
def status(job_id: str) -> None:
    path = runs_dir() / job_id / "status.json"
    if not path.is_file():
        typer.secho("not found", fg=typer.colors.RED)
        raise typer.Exit(1)
    st = read_status(path)
    typer.echo(f"{st.state} prompt_id={st.prompt_id} outputs={st.outputs}")

if __name__ == "__main__":
    app()
```

- [ ] **Step 2: 手工 smoke**

```bash
export COMFY_BASE_URL=http://127.0.0.1:9
comfy-orch doctor   # 应非 0 退出或报 ConnectionFailed
```

- [ ] **Step 3: README 补全双环境 + CLI**

写明：VM 真 ComfyUI 调模板不跑 H3；租卡出片；`COMFY_BASE_URL` 切换。

- [ ] **Step 4: Commit（若用户要求）**

---

### Task 8: 仓库内 demo 模板包

**Files:**
- Create: `templates/demo_txt/workflow_api.json`
- Create: `templates/demo_txt/bindings.yaml`
- Create: `templates/demo_txt/manifest.schema.yaml`
- Create: `examples/sample_job/job.yaml`（可选）

- [ ] **Step 1: 放入与 fixtures 同结构的 demo_txt**（仅文本字段，无媒体，便于 VM 上非 H3 小工作流对接）

`manifest.schema.yaml`:
```yaml
required_fields:
  - prompt
required_files: []
```

`bindings.yaml`:
```yaml
bindings:
  - field: prompt
    node_title: 正向提示词
    input: text
```

`workflow_api.json`: 与测试夹具相同的最小图（Title=正向提示词）。

- [ ] **Step 2: 全量测试**

Run: `pytest -v`  
Expected: 全部 PASS

- [ ] **Step 3: 更新 spec 状态为已批准（可选一行）**

将 spec 文首 `待审阅` 改为 `已批准`。

- [ ] **Step 4: Commit（若用户要求）**

```bash
git commit -m "$(cat <<'EOF'
docs: add demo template and finish CLI docs

EOF
)"
```

---

## Spec coverage checklist

| Spec 项 | Task |
|---------|------|
| Manifest 门禁 | 2 |
| Binder Title/ID | 3 |
| Comfy Client upload/prompt/history/view | 4 |
| Artifact 落盘 | 5–6 |
| Runner 状态机 / runs 状态 | 5–6 |
| CLI doctor/submit/status | 7 |
| Base URL only / 双环境说明 | 7 README |
| 轻量测试（单测+一条 mock 集成） | 2–6 |
| 不做开关机/隧道/inbox/H3 图 | 全计划未包含 |
| VM 真 ComfyUI 调通 | README + 双环境说明 |

## Self-review notes

- 第一期完成等待用**轮询**（比 WS 更好测）；与 spec「优先 WS」略有简化——若需严格对齐，在 Task 4 后加可选 `wait_until_done_ws`，默认仍轮询。  
- `retry` / `interrupt` 列为后续，本期 CLI 不实现（spec 为可选）。  
- 视频/音频无 upload API 时预置远端文件名：Binder 已支持非 media 字段直接写文件名；Runner 仅对 `media: true` 上传。

---

## Execution handoff

Plan complete and saved to:

`/home/linux_dev/projects/comfyui-h3-automation/docs/superpowers/plans/2026-09-08-comfyui-h3-remote-orchestration.md`

**项目根目录：** `/home/linux_dev/projects/comfyui-h3-automation`

Two execution options:

1. **Subagent-Driven（推荐）** — 每任务新开子代理，任务间复查  
2. **Inline Execution** — 本会话按 executing-plans 连续做  

Which approach?
