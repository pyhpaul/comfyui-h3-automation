"""Archive one successful U02 run and verify its Google Drive copy."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path


CONTENT = Path("/content")
ARCHIVE = CONTENT / "h3-u02-evidence.tar"
RECEIPT = CONTENT / "h3-u02-backup-receipt.json"
RCLONE = CONTENT / "rclone"
CONFIG = CONTENT / "rclone.conf"
REMOTE = "h3drive_h3:comfyui-h3-colab-dedicated/rental-20260924-5090/stage2"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hashes(path: Path) -> tuple[str, str]:
    sha = hashlib.sha256()
    md5 = hashlib.md5()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            sha.update(block)
            md5.update(block)
    return sha.hexdigest(), md5.hexdigest()


def run(*args: str) -> str:
    print("RUN", " ".join(args), flush=True)
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, flush=True)
    if result.stderr:
        print(result.stderr, flush=True)
    return result.stdout


def main() -> None:
    started = time.monotonic()
    started_at = utc_now()
    results = CONTENT / "h3-u02-results"
    metrics = CONTENT / "h3-u02-metrics"
    if not (results / "batch.json").is_file() or not (metrics / "u02-artifacts.json").is_file():
        raise RuntimeError("U02 results or captured metrics are missing")

    with tarfile.open(ARCHIVE, "w") as bundle:
        bundle.add(results, arcname=results.name)
        bundle.add(metrics, arcname=metrics.name)
    archived_at = time.monotonic()
    sha256, md5 = hashes(ARCHIVE)
    hashed_at = time.monotonic()

    remote_archive = f"{REMOTE}/{ARCHIVE.name}"
    run(str(RCLONE), "copyto", str(ARCHIVE), remote_archive,
        "--config", str(CONFIG), "--retries", "3", "--low-level-retries", "3")
    uploaded_at = time.monotonic()
    remote_md5 = run(str(RCLONE), "md5sum", remote_archive, "--config", str(CONFIG)).split()[0]
    if remote_md5 != md5:
        raise RuntimeError(f"Drive MD5 mismatch: local={md5} remote={remote_md5}")
    verified_at = time.monotonic()

    receipt = {
        "started_at_utc": started_at,
        "completed_at_utc": utc_now(),
        "archive": ARCHIVE.name,
        "archive_bytes": ARCHIVE.stat().st_size,
        "sha256": sha256,
        "md5": md5,
        "remote": remote_archive,
        "archive_seconds": round(archived_at - started, 3),
        "hash_seconds": round(hashed_at - archived_at, 3),
        "upload_seconds": round(uploaded_at - hashed_at, 3),
        "remote_verify_seconds": round(verified_at - uploaded_at, 3),
        "total_seconds": round(verified_at - started, 3),
    }
    RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    run(str(RCLONE), "copyto", str(RECEIPT), f"{REMOTE}/{RECEIPT.name}",
        "--config", str(CONFIG))
    print("BACKUP_VERIFIED", json.dumps(receipt), flush=True)


if __name__ == "__main__":
    main()
