import re

import pytest
from pytest_httpx import HTTPXMock

from comfy_orch.client import ComfyClient
from comfy_orch.errors import ConnectionFailed, QueueRejected


BASE = "http://comfy.test"


def test_system_stats_ok(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE}/system_stats", json={"system": {}})
    client = ComfyClient(BASE)
    try:
        assert client.system_stats()["system"] == {}
    finally:
        client.close()


def test_upload_image(httpx_mock: HTTPXMock, tmp_path):
    path = tmp_path / "a.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    httpx_mock.add_response(
        url=f"{BASE}/upload/image",
        method="POST",
        json={"name": "a.png", "subfolder": "", "type": "input"},
    )
    client = ComfyClient(BASE)
    try:
        assert client.upload_image(path) == "a.png"
    finally:
        client.close()


def test_queue_prompt(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}/prompt",
        method="POST",
        json={"prompt_id": "pid-1", "number": 1},
    )
    client = ComfyClient(BASE)
    try:
        assert client.queue_prompt({"1": {}}) == "pid-1"
    finally:
        client.close()


def test_upload_image_http_error(httpx_mock: HTTPXMock, tmp_path):
    path = tmp_path / "a.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    httpx_mock.add_response(url=f"{BASE}/upload/image", method="POST", status_code=503)
    client = ComfyClient(BASE)
    try:
        with pytest.raises(ConnectionFailed):
            client.upload_image(path)
    finally:
        client.close()


def test_queue_prompt_bad_json(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}/prompt",
        method="POST",
        status_code=200,
        content=b"not json",
    )
    client = ComfyClient(BASE)
    try:
        with pytest.raises(QueueRejected):
            client.queue_prompt({"1": {}})
    finally:
        client.close()


def test_queue_prompt_node_errors(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}/prompt",
        method="POST",
        status_code=200,
        json={"node_errors": {"1": {"errors": ["bad input"]}}},
    )
    client = ComfyClient(BASE)
    try:
        with pytest.raises(QueueRejected):
            client.queue_prompt({"1": {}})
    finally:
        client.close()


def test_wait_until_done_polls_history(httpx_mock: HTTPXMock):
    entry = {
        "outputs": {
            "9": {
                "images": [{"filename": "out.png", "subfolder": "", "type": "output"}]
            }
        }
    }
    httpx_mock.add_response(url=f"{BASE}/history/pid-1", json={})
    httpx_mock.add_response(url=f"{BASE}/history/pid-1", json={"pid-1": entry})
    client = ComfyClient(BASE)
    try:
        hist = client.wait_until_done("pid-1", poll_interval=0.01, timeout=1.0)
        assert "outputs" in hist
    finally:
        client.close()


def test_download_view(httpx_mock: HTTPXMock, tmp_path):
    httpx_mock.add_response(
        url=f"{BASE}/view",
        match_params={"filename": "out.png", "subfolder": "", "type": "output"},
        content=b"VIDEO",
    )
    client = ComfyClient(BASE)
    try:
        dest = tmp_path / "out.bin"
        result = client.download_view(filename="out.png", dest=dest)
        assert result == dest
        assert dest.read_bytes() == b"VIDEO"
    finally:
        client.close()


def test_download_view_url_regex(httpx_mock: HTTPXMock, tmp_path):
    httpx_mock.add_response(
        url=re.compile(r"http://comfy\.test/view\?.*filename=clip\.mp4"),
        content=b"BYTES",
    )
    client = ComfyClient(BASE)
    try:
        dest = tmp_path / "nested" / "clip.mp4"
        client.download_view(
            filename="clip.mp4",
            dest=dest,
            subfolder="videos",
            type_="output",
        )
        assert dest.read_bytes() == b"BYTES"
    finally:
        client.close()
