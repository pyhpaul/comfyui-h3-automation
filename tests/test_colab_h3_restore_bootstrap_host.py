"""Shared host preflight checks using only simulated Drive responses."""

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))
import colab_h3_restore_bootstrap_host as host


@pytest.fixture
def metadata():
    return json.loads((ROOT / "docs/ops/drive-rclone-bootstrap-v1.json").read_text())


def test_host_checks_metadata_before_verified_bootstrap(tmp_path, monkeypatch, metadata):
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(metadata))
    events = []

    def lookup(command, **kwargs):
        events.append("lookup")
        assert command[:3] == ["rclone", "lsjson", metadata["remote_path"]]
        assert "--hash" in command
        return json.dumps({"ID": metadata["file_id"], "Size": metadata["bytes"],
                           "Hashes": {"sha256": metadata["archive_sha256"]}})

    def install(config, asset, target):
        events.append("install")
        assert asset == metadata
        assert config == tmp_path / "config"
        target.write_bytes(b"verified bootstrap stub")

    monkeypatch.setattr(host, "run", lookup)
    monkeypatch.setattr(host.bootstrap, "bootstrap_from_drive", install)
    host.check_drive_bootstrap(tmp_path / "config", path, tmp_path / "runs")
    assert events == ["lookup", "install"]
    report_path = next((tmp_path / "runs").glob("*/report.json"))
    report = json.loads(report_path.read_text())
    assert report["state"] == "success"
    assert report["paid_started"] is False
    assert report["binary_sha256"] == metadata["binary_sha256"]


@pytest.mark.parametrize("field", ["ID", "Size", "Hashes"])
def test_changed_remote_asset_stops_before_download(tmp_path, monkeypatch, metadata, field):
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(metadata))
    remote = {"ID": metadata["file_id"], "Size": metadata["bytes"],
              "Hashes": {"sha256": metadata["archive_sha256"]}}
    remote[field] = {"sha256": "wrong"} if field == "Hashes" else "wrong"
    monkeypatch.setattr(host, "run", lambda *args, **kwargs: json.dumps(remote))
    monkeypatch.setattr(host.bootstrap, "bootstrap_from_drive",
                        lambda *args: pytest.fail("mismatched asset must not download"))
    with pytest.raises(RuntimeError, match="pinned metadata"):
        host.check_drive_bootstrap(tmp_path / "config", path, tmp_path / "runs")
    assert not (tmp_path / "runs").exists()


def test_bootstrap_hash_failure_cannot_write_success_report(tmp_path, monkeypatch, metadata):
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(metadata))
    monkeypatch.setattr(host, "run", lambda *args, **kwargs: json.dumps({
        "ID": metadata["file_id"], "Size": metadata["bytes"],
        "Hashes": {"sha256": metadata["archive_sha256"]}}))

    def mismatch(*args):
        raise RuntimeError("rclone binary SHA-256 mismatch")

    monkeypatch.setattr(host.bootstrap, "bootstrap_from_drive", mismatch)
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        host.check_drive_bootstrap(tmp_path / "config", path, tmp_path / "runs")
    assert not list((tmp_path / "runs").glob("*/report.json"))
