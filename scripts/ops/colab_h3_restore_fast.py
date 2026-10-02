"""Opt-in bounded part prefetch; preserve serial restore and full hash gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import colab_h3_restore as base


OUTPUT_LOCK = threading.Lock()


def emit(message: str) -> None:
    with OUTPUT_LOCK:
        print(message, flush=True)


@dataclass(frozen=True)
class RestoreOptions:
    workers: int = 4
    part_timeout: int = 180

    def __post_init__(self) -> None:
        if not 1 <= self.workers <= 8:
            raise ValueError("workers must be in [1, 8]")
        if self.part_timeout <= 0:
            raise ValueError("part_timeout must be positive")


@dataclass(frozen=True)
class DownloadedPart:
    path: Path
    reused: bool
    seconds: float


def download_part(cache: Path, relative_path: str, index: int, expected_size: int,
                  options: RestoreOptions) -> DownloadedPart:
    target = cache / f"part-{index:03d}"
    if target.is_file() and target.stat().st_size == expected_size:
        return DownloadedPart(target, True, 0.0)
    staging = target.with_suffix(".download")
    command = [str(base.RCLONE), "copyto",
               f"{base.REMOTE}/model-parts/{relative_path}/part-{index:03d}",
               str(staging), "--config", str(base.CONFIG),
               "--retries", "3", "--low-level-retries", "3"]
    started = time.monotonic()
    try:
        staging.unlink(missing_ok=True)
        emit("RUN " + " ".join(command))
        subprocess.run(command, check=True, timeout=options.part_timeout)
        if staging.stat().st_size != expected_size:
            raise RuntimeError(f"wrong part size: {relative_path} part-{index:03d}")
        staging.replace(target)
        return DownloadedPart(target, False, time.monotonic() - started)
    finally:
        staging.unlink(missing_ok=True)


def append_part(path: Path, assembled, digest) -> int:
    copied = 0
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            assembled.write(block)
            digest.update(block)
            copied += len(block)
    return copied


def assemble_prefetched(cache: Path, output: Path, relative_path: str,
                        expected_size: int, digest, options: RestoreOptions) -> dict:
    count = (expected_size + base.PART_SIZE - 1) // base.PART_SIZE
    metrics = {"bytes": 0, "reused_parts": 0, "parts": count,
               "wait_seconds": 0.0, "assembly_seconds": 0.0,
               "download_task_seconds": 0.0}

    def submit(pool, index):
        size = min(base.PART_SIZE, expected_size - index * base.PART_SIZE)
        return pool.submit(download_part, cache, relative_path, index, size, options)

    with ThreadPoolExecutor(max_workers=options.workers) as pool:
        pending = {index: submit(pool, index) for index in range(min(count, options.workers))}
        try:
            with output.open("wb") as assembled:
                for index in range(count):
                    started = time.monotonic()
                    part = pending.pop(index).result()
                    metrics["wait_seconds"] += time.monotonic() - started
                    metrics["reused_parts"] += int(part.reused)
                    metrics["download_task_seconds"] += part.seconds
                    started = time.monotonic()
                    metrics["bytes"] += append_part(part.path, assembled, digest)
                    metrics["assembly_seconds"] += time.monotonic() - started
                    next_index = index + options.workers
                    if next_index < count:
                        pending[next_index] = submit(pool, next_index)
                    emit(f"model_part {relative_path} {index + 1} {count}")
        finally:
            for future in pending.values():
                future.cancel()
    return metrics


def clear_model_cache(cache: Path, count: int) -> None:
    for index in range(count):
        (cache / f"part-{index:03d}").unlink(missing_ok=True)
    if not any(cache.iterdir()):
        cache.rmdir()


def restore_split_model(models: Path, relative_path: str, expected_size: int,
                        expected_sha256: str, *, options: RestoreOptions) -> None:
    if expected_size <= 0:
        raise ValueError("expected_size must be positive")
    output = models / relative_path
    if (output.is_file() and output.stat().st_size == expected_size
            and base.sha256(output) == expected_sha256):
        emit(f"model_cached_verified {relative_path}")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_name(output.name + ".incomplete")
    cache = base.CONTENT / "h3-part-cache" / expected_sha256
    cache.mkdir(parents=True, exist_ok=True)
    count = (expected_size + base.PART_SIZE - 1) // base.PART_SIZE
    started = time.monotonic()
    digest = hashlib.sha256()
    try:
        metrics = assemble_prefetched(cache, staging, relative_path,
                                       expected_size, digest, options)
        if metrics["bytes"] != expected_size or digest.hexdigest() != expected_sha256:
            clear_model_cache(cache, count)
            raise RuntimeError(f"reassembled model mismatch: {relative_path}")
        staging.replace(output)
        clear_model_cache(cache, count)
        metrics.update({"model": relative_path, "workers": options.workers,
                        "seconds": time.monotonic() - started,
                        "sha256": digest.hexdigest()})
        emit("fast_model_metrics " + json.dumps(metrics))
    finally:
        staging.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--part-timeout", type=int, default=180)
    args = parser.parse_args()
    options = RestoreOptions(args.workers, args.part_timeout)
    base.main(restore_model=partial(restore_split_model, options=options))


if __name__ == "__main__":
    main()
