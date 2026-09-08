from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from pathlib import Path

from comfy_orch.errors import ComfyOrchError
from comfy_orch.runner import submit_job


def discover_inbox_jobs(inbox_dir: Path) -> list[Path]:
    """Return ready job dirs under inbox (contain job.yaml). Skip .done/.failed."""
    if not inbox_dir.is_dir():
        return []
    jobs: list[Path] = []
    for child in sorted(inbox_dir.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        if (child / "job.yaml").is_file():
            jobs.append(child)
    return jobs


def _move_job(job_dir: Path, dest_root: Path) -> Path:
    dest_root.mkdir(parents=True, exist_ok=True)
    target = dest_root / job_dir.name
    if target.exists():
        target = dest_root / f"{job_dir.name}-{int(time.time())}"
    shutil.move(str(job_dir), str(target))
    return target


def process_inbox_once(
    inbox_dir: Path,
    *,
    base_url: str,
    root: Path,
    submit: Callable[..., str] = submit_job,
) -> list[tuple[Path, str | None, str | None]]:
    """
    Process each ready job once.
    Returns list of (job_dir_after_move, job_id_or_None, error_or_None).
    """
    results: list[tuple[Path, str | None, str | None]] = []
    done_dir = inbox_dir / ".done"
    failed_dir = inbox_dir / ".failed"
    for job_dir in discover_inbox_jobs(inbox_dir):
        try:
            job_id = submit(job_dir, base_url=base_url, root=root)
            moved = _move_job(job_dir, done_dir)
            results.append((moved, job_id, None))
        except ComfyOrchError as exc:
            moved = _move_job(job_dir, failed_dir)
            results.append((moved, None, str(exc)))
    return results


def watch_inbox(
    inbox_dir: Path,
    *,
    base_url: str,
    root: Path,
    interval: float = 5.0,
    once: bool = False,
    submit: Callable[..., str] = submit_job,
) -> None:
    inbox_dir.mkdir(parents=True, exist_ok=True)
    while True:
        process_inbox_once(inbox_dir, base_url=base_url, root=root, submit=submit)
        if once:
            return
        time.sleep(interval)
