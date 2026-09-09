from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from comfy_orch.errors import CollectFailed, ConnectionFailed, ExecutionFailed, QueueRejected


class ComfyClient:
    def __init__(self, base_url: str, timeout: float = 60.0, client_id: str | None = None):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)
        self.client_id = client_id if client_id else str(uuid.uuid4())

    def close(self) -> None:
        self._client.close()

    def system_stats(self) -> dict[str, Any]:
        try:
            r = self._client.get("/system_stats")
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise ConnectionFailed(str(e)) from e

    def upload_image(
        self,
        path: Path,
        overwrite: bool = True,
        *,
        retries: int = 3,
        retry_backoff: float = 0.5,
    ) -> str:
        last_error: Exception | None = None
        attempts = max(1, retries)
        for attempt in range(attempts):
            try:
                with path.open("rb") as f:
                    r = self._client.post(
                        "/upload/image",
                        files={"image": (path.name, f, "application/octet-stream")},
                        data={"overwrite": "true" if overwrite else "false"},
                    )
                r.raise_for_status()
                return r.json()["name"]
            except httpx.HTTPError as e:
                last_error = e
                if attempt + 1 >= attempts:
                    break
                time.sleep(retry_backoff * (attempt + 1))
        assert last_error is not None
        raise ConnectionFailed(str(last_error)) from last_error

    def queue_prompt(self, workflow: dict[str, Any]) -> str:
        try:
            r = self._client.post(
                "/prompt",
                json={"prompt": workflow, "client_id": self.client_id},
            )
        except httpx.HTTPError as e:
            raise ConnectionFailed(str(e)) from e
        try:
            data = r.json()
        except ValueError as e:
            raise QueueRejected(str(e)) from e
        if r.status_code >= 400 or data.get("node_errors"):
            raise QueueRejected(str(data))
        try:
            return data["prompt_id"]
        except KeyError as e:
            raise QueueRejected(str(e)) from e

    def wait_until_done(
        self,
        prompt_id: str,
        *,
        poll_interval: float = 1.0,
        timeout: float = 3600.0,
    ) -> dict[str, Any]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                r = self._client.get(f"/history/{prompt_id}")
                r.raise_for_status()
                data = r.json()
            except httpx.HTTPError as e:
                raise ConnectionFailed(str(e)) from e
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
