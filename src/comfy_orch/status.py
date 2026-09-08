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
    return JobStatus(
        job_id=data["job_id"],
        state=data["state"],
        prompt_id=data.get("prompt_id"),
        message=data.get("message", ""),
        outputs=list(data.get("outputs") or []),
        extra=dict(data.get("extra") or {}),
    )
