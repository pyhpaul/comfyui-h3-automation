import json
import shutil
from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock

from comfy_orch.errors import ValidationError
from comfy_orch.runner import submit_job
from comfy_orch.status import read_status

BASE = "http://comfy.test"
FIXTURES = Path(__file__).parent / "fixtures" / "templates" / "demo"


def _install_demo_template(root: Path) -> None:
    dest = root / "templates" / "demo"
    dest.mkdir(parents=True)
    for name in ("bindings.yaml", "manifest.schema.yaml", "workflow_api.json"):
        shutil.copy(FIXTURES / name, dest / name)


def test_runner_rejects_missing_file_without_comfy(httpx_mock: HTTPXMock, tmp_path: Path):
    _install_demo_template(tmp_path)
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "job.yaml").write_text(
        "template: demo\nfields:\n  prompt: hello\n  first_frame: assets/missing.png\n",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="first_frame"):
        submit_job(job_dir, base_url=BASE, root=tmp_path)

    assert len(httpx_mock.get_requests()) == 0
    run_dirs = list((tmp_path / "runs").iterdir())
    assert len(run_dirs) == 1
    st = read_status(run_dirs[0] / "status.json")
    assert st.state == "failed"
    assert "first_frame" in st.message


def test_runner_missing_bindings_marks_failed(httpx_mock: HTTPXMock, tmp_path: Path):
    dest = tmp_path / "templates" / "demo"
    dest.mkdir(parents=True)
    for name in ("manifest.schema.yaml", "workflow_api.json"):
        shutil.copy(FIXTURES / name, dest / name)
    job_dir = tmp_path / "job"
    (job_dir / "assets").mkdir(parents=True)
    (job_dir / "assets" / "ref.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (job_dir / "job.yaml").write_text(
        "template: demo\nfields:\n  prompt: hello\n  first_frame: assets/ref.png\n",
        encoding="utf-8",
    )
    httpx_mock.add_response(url=f"{BASE}/system_stats", json={"system": {}})

    with pytest.raises(ValidationError, match="bindings.yaml"):
        submit_job(job_dir, base_url=BASE, root=tmp_path)

    run_dirs = list((tmp_path / "runs").iterdir())
    st = read_status(run_dirs[0] / "status.json")
    assert st.state == "failed"
    assert "bindings.yaml" in st.message


def test_runner_happy_path(httpx_mock: HTTPXMock, tmp_path: Path):
    _install_demo_template(tmp_path)
    job_dir = tmp_path / "job"
    (job_dir / "assets").mkdir(parents=True)
    (job_dir / "assets" / "ref.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (job_dir / "job.yaml").write_text(
        "template: demo\nfields:\n  prompt: hello\n  first_frame: assets/ref.png\n",
        encoding="utf-8",
    )

    history_entry = {
        "outputs": {
            "9": {
                "images": [{"filename": "out.png", "subfolder": "", "type": "output"}]
            }
        }
    }
    httpx_mock.add_response(url=f"{BASE}/system_stats", json={"system": {}})
    httpx_mock.add_response(
        url=f"{BASE}/upload/image",
        method="POST",
        json={"name": "ref.png", "subfolder": "", "type": "input"},
    )
    httpx_mock.add_response(
        url=f"{BASE}/prompt",
        method="POST",
        json={"prompt_id": "pid-1", "number": 1},
    )
    httpx_mock.add_response(url=f"{BASE}/history/pid-1", json={"pid-1": history_entry})
    httpx_mock.add_response(
        url=f"{BASE}/view",
        match_params={"filename": "out.png", "subfolder": "", "type": "output"},
        content=b"VIDEO",
    )

    job_id = submit_job(job_dir, base_url=BASE, root=tmp_path)

    st = read_status(tmp_path / "runs" / job_id / "status.json")
    assert st.state == "done"
    assert st.prompt_id == "pid-1"
    assert st.outputs
    out_path = tmp_path / "outputs" / job_id / "out.png"
    assert out_path.is_file()
    assert out_path.read_bytes() == b"VIDEO"
    assert str(out_path) in st.outputs

    prompt_req = httpx_mock.get_requests()[2]
    body = json.loads(prompt_req.content.decode())
    assert body["prompt"]["6"]["inputs"]["text"] == "hello"
    assert body["prompt"]["10"]["inputs"]["image"] == "ref.png"
