from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from pytest_httpx import HTTPXMock

from comfy_orch.client import ComfyClient
from comfy_orch.errors import ConnectionFailed, ValidationError
from comfy_orch.inbox import discover_inbox_jobs, process_inbox_once


def test_upload_image_retries_then_succeeds(httpx_mock: HTTPXMock, tmp_path: Path):
    path = tmp_path / "a.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    httpx_mock.add_response(
        url="http://comfy.test/upload/image",
        method="POST",
        status_code=503,
    )
    httpx_mock.add_response(
        url="http://comfy.test/upload/image",
        method="POST",
        json={"name": "a.png", "subfolder": "", "type": "input"},
    )
    c = ComfyClient("http://comfy.test")
    try:
        assert c.upload_image(path, retries=3, retry_backoff=0.01) == "a.png"
    finally:
        c.close()
    assert len(httpx_mock.get_requests()) == 2


def test_upload_image_retries_exhausted(httpx_mock: HTTPXMock, tmp_path: Path):
    path = tmp_path / "a.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    for _ in range(3):
        httpx_mock.add_response(
            url="http://comfy.test/upload/image",
            method="POST",
            status_code=503,
        )
    c = ComfyClient("http://comfy.test")
    try:
        with pytest.raises(ConnectionFailed):
            c.upload_image(path, retries=3, retry_backoff=0.01)
    finally:
        c.close()
    assert len(httpx_mock.get_requests()) == 3


def test_discover_and_process_inbox(tmp_path: Path):
    inbox = tmp_path / "inbox"
    job = inbox / "job1"
    job.mkdir(parents=True)
    (job / "job.yaml").write_text("template: demo\nfields: {}\n", encoding="utf-8")
    (inbox / "notes.txt").write_text("ignore", encoding="utf-8")
    (inbox / ".done").mkdir()

    assert [p.name for p in discover_inbox_jobs(inbox)] == ["job1"]

    submit = MagicMock(return_value="jid-1")
    results = process_inbox_once(
        inbox,
        base_url="http://comfy.test",
        root=tmp_path,
        submit=submit,
    )
    assert len(results) == 1
    moved, job_id, err = results[0]
    assert job_id == "jid-1"
    assert err is None
    assert moved.parent.name == ".done"
    assert not job.exists()
    submit.assert_called_once()


def test_process_inbox_passes_client_id(tmp_path: Path):
    inbox = tmp_path / "inbox"
    job = inbox / "j1"
    job.mkdir(parents=True)
    (job / "job.yaml").write_text("template: x\nfields: {}\n", encoding="utf-8")
    seen: dict = {}

    def fake_submit(job_dir, *, base_url, root, client_id=None):
        seen["client_id"] = client_id
        return "abc123"

    process_inbox_once(
        inbox,
        base_url="http://comfy.test",
        root=tmp_path,
        submit=fake_submit,
        client_id="from-cli",
    )
    assert seen["client_id"] == "from-cli"


def test_process_inbox_moves_failed(tmp_path: Path):
    inbox = tmp_path / "inbox"
    job = inbox / "bad"
    job.mkdir(parents=True)
    (job / "job.yaml").write_text("template: demo\nfields: {}\n", encoding="utf-8")

    def boom(*_a, **_k):
        raise ValidationError("nope")

    results = process_inbox_once(
        inbox,
        base_url="http://comfy.test",
        root=tmp_path,
        submit=boom,
    )
    assert results[0][1] is None
    assert "nope" in (results[0][2] or "")
    assert results[0][0].parent.name == ".failed"
