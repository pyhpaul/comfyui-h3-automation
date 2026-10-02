"""Identity-bound phase receipts, published only after evidence verification."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class ReceiptIdentity:
    session_id: str
    label: str
    attempt_id: str
    input_manifest_sha256: str


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity_from_environment(label: str, manifest: Path) -> ReceiptIdentity:
    actual = file_sha256(manifest)
    expected = os.environ.get("H3_INPUT_MANIFEST_SHA256", actual)
    if actual != expected:
        raise RuntimeError("preflight manifest changed since host admission")
    return ReceiptIdentity(
        session_id=os.environ.get("H3_SESSION_ID", "legacy"),
        label=label,
        attempt_id=os.environ.get("H3_ATTEMPT_ID", "legacy"),
        input_manifest_sha256=actual,
    )


def receipt_status(receipt: dict, identity: ReceiptIdentity,
                   attempted_at: datetime) -> str:
    for key, value in vars(identity).items():
        if receipt.get(key) != value:
            return f"wrong_{key}"
    try:
        started = datetime.fromisoformat(receipt["started_at_utc"])
    except (KeyError, TypeError, ValueError):
        return "invalid_timestamp"
    if started.tzinfo is None or started < attempted_at - timedelta(seconds=5):
        return "stale"
    if receipt.get("archive_state") != "verified":
        return "unverified_archive"
    return str(receipt.get("state", "unknown"))


def publish_verified(output: Path, remote: str, rclone: Path,
                     config: Path, timeout: int = 300) -> None:
    phase = output / "phase.json"
    receipt = json.loads(phase.read_text())
    if receipt.get("state") not in {"success", "failed"}:
        raise RuntimeError("phase receipt must have a terminal state")
    base = [str(rclone), "--config", str(config)]
    excluded = ["--exclude", "phase.json"]
    subprocess.run([*base, "copy", str(output), remote, *excluded,
                    "--transfers", "2", "--checkers", "2"], check=True,
                   timeout=timeout)
    subprocess.run([*base, "check", remote, str(output), *excluded],
                   check=True, timeout=timeout)
    receipt["archive_state"] = "verified"
    phase.write_text(json.dumps(receipt, indent=2) + "\n")
    subprocess.run([*base, "copyto", str(phase), f"{remote}/phase.json"],
                   check=True, timeout=min(timeout, 120))
    confirmed = subprocess.run([*base, "cat", f"{remote}/phase.json"],
                               capture_output=True, check=True,
                               timeout=min(timeout, 30))
    if confirmed.stdout != phase.read_bytes():
        raise RuntimeError("remote terminal receipt does not match local receipt")
