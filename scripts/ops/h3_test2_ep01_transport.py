"""Stage rclone and the G4 wheel without large Colab CLI file uploads."""

from __future__ import annotations

import gzip
import hashlib
import os
import shutil
import subprocess
import time
from pathlib import Path


CONTENT = Path("/content")
CONFIG = CONTENT / "rclone.conf"
RCLONE_GZ = CONTENT / "rclone.gz"
WHEEL_REMOTE = (
    "h3drive_h3:comfyui-h3-colab-dedicated/standard-v1/runtime/g4-sm120/"
    "sageattention-2.2.0-cp313-cp313-linux_x86_64.whl"
)
WHEEL = CONTENT / "sageattention-2.2.0-cp313-cp313-linux_x86_64.whl"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    expected_wheel = os.environ["H3_G4_WHEEL_SHA256"]
    if not CONFIG.is_file() or WHEEL.exists() or RCLONE_GZ.exists():
        raise RuntimeError("transport input missing or destination already exists")
    started = time.monotonic()
    subprocess.run(["apt-get", "install", "-y", "rclone"], check=True, timeout=180)
    system_rclone = Path(shutil.which("rclone") or "")
    if not system_rclone.is_file():
        raise RuntimeError("apt rclone is not available")
    os.chmod(CONFIG, 0o600)
    subprocess.run([str(system_rclone), "about", "h3drive_h3:",
                    "--config", str(CONFIG)], check=True, timeout=40)
    subprocess.run([str(system_rclone), "copyto", WHEEL_REMOTE, str(WHEEL),
                    "--config", str(CONFIG), "--retries", "3"],
                   check=True, timeout=300)
    if sha256(WHEEL) != expected_wheel:
        raise RuntimeError("Drive G4 SageAttention wheel hash mismatch")
    with system_rclone.open("rb") as source, gzip.open(RCLONE_GZ, "wb", compresslevel=1) as target:
        shutil.copyfileobj(source, target, length=8 * 1024 * 1024)
    print("TEST2_TRANSPORT_READY", {
        "wheel_sha256": expected_wheel,
        "rclone_path": str(system_rclone),
        "rclone_gz_bytes": RCLONE_GZ.stat().st_size,
        "seconds": round(time.monotonic() - started, 2),
    }, flush=True)


if __name__ == "__main__":
    main()
