import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/episode_post"))

from verify_project_assets import project_path, verify_assets


def test_accepted_public_asset_is_hash_verified():
    manifest = json.loads((ROOT / "assets/episode_post/manifest.json").read_text())
    assert verify_assets(ROOT, manifest)["checked"] == ["bloom-hold-suspense-v1-preview"]


def test_library_points_to_project_owned_binary():
    preset = json.loads((ROOT / "docs/ending-presets/bloom-hold-suspense-v1.json").read_text())
    manifest = json.loads((ROOT / "assets/episode_post/manifest.json").read_text())
    asset = manifest["assets"][0]
    assert preset["preview"]["path"] == asset["path"]
    assert preset["preview"]["sha256"] == asset["sha256"]
    assert preset["id"] == asset["ending_preset_id"]
    assert preset["timeline_seconds"]["motion_end"] + 1 == preset["timeline_seconds"]["card_start"]


def test_hash_mismatch_blocks_asset_use(tmp_path):
    (tmp_path / "clip.mp4").write_bytes(b"changed")
    manifest = {"schema": "episode-post-assets/v1", "assets": [
        {"id": "clip", "visibility": "public", "path": "clip.mp4",
         "sha256": hashlib.sha256(b"original").hexdigest()}]}
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_assets(tmp_path, manifest)


@pytest.mark.parametrize("path", ["../outside.mp4", "/outside.mp4"])
def test_asset_path_must_stay_in_project(tmp_path, path):
    with pytest.raises(ValueError, match="escapes project"):
        project_path(tmp_path, path)


def test_private_media_is_explicit_and_optional(tmp_path):
    manifest = {"schema": "episode-post-assets/v1", "assets": [
        {"id": "private", "visibility": "local", "path": "missing.mp4", "sha256": "0" * 64}]}
    assert verify_assets(tmp_path, manifest)["checked"] == []
    with pytest.raises(FileNotFoundError):
        verify_assets(tmp_path, manifest, include_local=True)
