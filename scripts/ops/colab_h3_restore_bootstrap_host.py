"""Validate the pinned Drive bootstrap before any paid Colab allocation."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from colab_h3_a100_ab_host import run
import colab_h3_restore_bootstrap as bootstrap


def check_drive_bootstrap(config: Path, metadata_path: Path, evidence_root: Path) -> None:
    metadata = json.loads(metadata_path.read_text())
    # Metadata lookup also lets rclone refresh the token before VM upload.
    output = run(["rclone", "lsjson", metadata["remote_path"], "--stat", "--hash",
                  "--config", str(config)], timeout=30)
    remote = json.loads(output)
    if (remote["ID"] != metadata["file_id"] or remote["Size"] != metadata["bytes"]
            or remote["Hashes"].get("sha256") != metadata["archive_sha256"]):
        raise RuntimeError("live Drive bootstrap does not match pinned metadata")
    folder = evidence_root / ("restore-bootstrap-check-" +
                              datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f"))
    folder.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    bootstrap.bootstrap_from_drive(config, metadata, folder / "rclone.gz")
    report = {"state": "success", "paid_started": False,
              "seconds": time.monotonic() - started,
              "archive_sha256": metadata["archive_sha256"],
              "binary_sha256": metadata["binary_sha256"]}
    (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("DRIVE_BOOTSTRAP_CHECK_OK", json.dumps(report), flush=True)
