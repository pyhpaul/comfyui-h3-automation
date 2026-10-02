"""Offline checks for the source-controlled Drive restore contract."""

import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))
import colab_h3_restore as restore


def test_large_model_manifest_matches_restore_script():
    manifest = json.loads((ROOT / "docs/ops/drive-restore-rental-20260924-v1.json").read_text())
    actual = {(item["relative_path"], item["bytes"], item["sha256"])
              for item in manifest["models"] if item["storage"] == "model-parts"}
    assert actual == set(restore.LARGE_MODELS)
    assert manifest["model_part_bytes"] == restore.PART_SIZE
    assert sum(item["bytes"] for item in manifest["models"]) == manifest["model_total_bytes"]


def test_split_model_requires_exact_bytes_and_digest(tmp_path, monkeypatch):
    payload = b"abcdefghij"
    parts = [payload[:4], payload[4:8], payload[8:]]
    monkeypatch.setattr(restore, "CONTENT", tmp_path)
    monkeypatch.setattr(restore, "PART_SIZE", 4)
    seen = []

    def fake_run(*args):
        index = int(args[2].rsplit("-", 1)[1])
        seen.append(index)
        (tmp_path / "h3-model-part.tmp").write_bytes(parts[index])

    monkeypatch.setattr(restore, "run", fake_run)
    digest = hashlib.sha256(payload).hexdigest()
    restore.restore_split_model(tmp_path / "models", "x/model.safetensors", len(payload), digest)
    assert seen == [0, 1, 2]
    assert (tmp_path / "models/x/model.safetensors").read_bytes() == payload


def test_split_model_does_not_publish_bad_digest(tmp_path, monkeypatch):
    monkeypatch.setattr(restore, "CONTENT", tmp_path)
    monkeypatch.setattr(restore, "PART_SIZE", 4)

    def fake_run(*args):
        (tmp_path / "h3-model-part.tmp").write_bytes(b"bad!")

    monkeypatch.setattr(restore, "run", fake_run)
    with pytest.raises(RuntimeError, match="reassembled model mismatch"):
        restore.restore_split_model(tmp_path / "models", "x/model.safetensors", 4,
                                    hashlib.sha256(b"good").hexdigest())
    assert not (tmp_path / "models/x/model.safetensors").exists()
