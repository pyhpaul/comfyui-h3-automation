"""Fetch the exact frozen rclone binary on the VM, not through CLI upload."""

from __future__ import annotations

import gzip
import configparser
import hashlib
import io
import json
import time
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen


VERSION = "1.75.1"
URL = f"https://downloads.rclone.org/v{VERSION}/rclone-v{VERSION}-linux-amd64.zip"
BINARY_SHA256 = "f66d8c1d552ad90296a11bc8b46d56a7fa5da1a7fa05e7ca522d95df92c4a4c0"


def install_archive(archive: bytes, target: Path, expected_sha256: str) -> None:
    staging = target.with_suffix(".incomplete")
    digest = hashlib.sha256()
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            name = f"rclone-v{VERSION}-linux-amd64/rclone"
            if bundle.getinfo(name).file_size > 160 * 1024 ** 2:
                raise RuntimeError("rclone binary exceeds bootstrap size limit")
            with bundle.open(name) as source, gzip.open(staging, "wb", compresslevel=1) as output:
                for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
                    digest.update(chunk)
                    output.write(chunk)
        if digest.hexdigest() != expected_sha256:
            raise RuntimeError("downloaded rclone does not match frozen binary SHA-256")
        staging.replace(target)
    finally:
        staging.unlink(missing_ok=True)


def install_gzip(data: bytes, target: Path, archive_sha256: str, binary_sha256: str) -> None:
    if hashlib.sha256(data).hexdigest() != archive_sha256:
        raise RuntimeError("rclone archive SHA-256 mismatch")
    digest = hashlib.sha256()
    size = 0
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as binary:
        for chunk in iter(lambda: binary.read(8 * 1024 * 1024), b""):
            size += len(chunk)
            if size > 160 * 1024 ** 2:
                raise RuntimeError("rclone binary exceeds bootstrap size limit")
            digest.update(chunk)
    if digest.hexdigest() != binary_sha256:
        raise RuntimeError("rclone binary SHA-256 mismatch")
    staging = target.with_suffix(".incomplete")
    try:
        staging.write_bytes(data)
        staging.replace(target)
    finally:
        staging.unlink(missing_ok=True)


def fetch_drive_archive(config: Path, file_id: str) -> bytes:
    if not file_id or not all(c.isalnum() or c in "-_" for c in file_id):
        raise ValueError("invalid Drive bootstrap file ID")
    parser = configparser.ConfigParser(interpolation=None)
    if not parser.read(config):
        raise RuntimeError("Drive bootstrap configuration is missing")
    token = json.loads(parser["h3drive_h3"]["token"])["access_token"]
    request = Request(f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media",
                      headers={"Authorization": f"Bearer {token}"})
    with urlopen(request, timeout=45) as response:
        archive = response.read(40 * 1024 ** 2 + 1)
    if len(archive) > 40 * 1024 ** 2:
        raise RuntimeError("rclone archive exceeds bootstrap size limit")
    return archive


def bootstrap_from_drive(config: Path, metadata: dict, target: Path) -> None:
    if metadata["binary_sha256"] != BINARY_SHA256 or metadata["version"] != VERSION:
        raise RuntimeError("Drive bootstrap metadata does not match frozen rclone")
    archive = fetch_drive_archive(config, metadata["file_id"])
    if len(archive) != metadata["bytes"]:
        raise RuntimeError("Drive bootstrap archive size mismatch")
    install_gzip(archive, target, metadata["archive_sha256"], BINARY_SHA256)


def main() -> None:
    started = time.monotonic()
    metadata_path = Path("/content/rclone-bootstrap.json")
    if metadata_path.is_file():
        bootstrap_from_drive(Path("/content/rclone.conf"), json.loads(metadata_path.read_text()),
                             Path("/content/rclone.gz"))
    else:
        with urlopen(URL, timeout=45) as response:
            archive = response.read(40 * 1024 ** 2 + 1)
        if len(archive) > 40 * 1024 ** 2:
            raise RuntimeError("rclone archive exceeds bootstrap size limit")
        install_archive(archive, Path("/content/rclone.gz"), BINARY_SHA256)
    print("RCLONE_BOOTSTRAP_OK", BINARY_SHA256,
          "seconds", round(time.monotonic() - started, 2), flush=True)


if __name__ == "__main__":
    main()
