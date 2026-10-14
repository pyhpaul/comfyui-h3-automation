"""Exact binary pin and atomic bootstrap publication, without network calls."""

import gzip
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
import colab_h3_restore_bootstrap as bootstrap


def archive(payload):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as bundle:
        bundle.writestr(f"rclone-v{bootstrap.VERSION}-linux-amd64/rclone", payload)
    return stream.getvalue()


def test_frozen_binary_is_compressed_only_after_verification(tmp_path):
    payload = b"frozen-rclone-binary"
    target = tmp_path / "rclone.gz"
    bootstrap.install_archive(archive(payload), target, hashlib.sha256(payload).hexdigest())
    assert gzip.decompress(target.read_bytes()) == payload
    assert not target.with_suffix(".incomplete").exists()


def test_bad_binary_never_replaces_existing_archive(tmp_path):
    target = tmp_path / "rclone.gz"
    target.write_bytes(b"original")
    with pytest.raises(RuntimeError, match="frozen binary SHA-256"):
        bootstrap.install_archive(archive(b"bad"), target, hashlib.sha256(b"good").hexdigest())
    assert target.read_bytes() == b"original"
    assert not target.with_suffix(".incomplete").exists()


def test_drive_gzip_requires_both_archive_and_binary_hash(tmp_path):
    binary = b"frozen-rclone-binary"
    data = gzip.compress(binary)
    target = tmp_path / "rclone.gz"
    archive_hash = hashlib.sha256(data).hexdigest()
    binary_hash = hashlib.sha256(binary).hexdigest()
    bootstrap.install_gzip(data, target, archive_hash, binary_hash)
    assert target.read_bytes() == data
    target.write_bytes(b"original")
    with pytest.raises(RuntimeError, match="archive SHA-256"):
        bootstrap.install_gzip(data, target, "0" * 64, binary_hash)
    assert target.read_bytes() == b"original"
    with pytest.raises(RuntimeError, match="binary SHA-256"):
        bootstrap.install_gzip(data, target, archive_hash, "0" * 64)
    assert target.read_bytes() == b"original"


def test_drive_fetch_uses_only_existing_scoped_access_token(tmp_path, monkeypatch):
    config = tmp_path / "rclone.conf"
    config.write_text("[h3drive_h3]\ntoken = " + json.dumps({"access_token": "test-token"}) + "\n")
    seen = []

    def fetch(request, **kwargs):
        seen.append((request.full_url, request.get_header("Authorization"), kwargs["timeout"]))
        return io.BytesIO(b"archive")

    monkeypatch.setattr(bootstrap, "urlopen", fetch)
    assert bootstrap.fetch_drive_archive(config, "test-file-id") == b"archive"
    assert seen == [("https://www.googleapis.com/drive/v3/files/test-file-id?alt=media",
                     "Bearer test-token", 45)]


def test_drive_fetch_rejects_unsafe_file_id(tmp_path):
    with pytest.raises(ValueError, match="file ID"):
        bootstrap.fetch_drive_archive(tmp_path / "absent.conf", "id?other=1")
