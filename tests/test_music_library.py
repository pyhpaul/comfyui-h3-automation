from copy import deepcopy
import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/episode_post"))
from import_music_library import AudioLinks
from verify_music_library import verify_catalog
from import_incompetech_batch import merge_entries
from import_music_library import download


def fixture_catalog(tmp_path):
    path = tmp_path / "fixture.bin"
    path.write_bytes(b"fixture")
    record = {"path": path.name, "sha256": hashlib.sha256(b"fixture").hexdigest(), "bytes": 7}
    track = {**record, "id": "test", "license": {"id": "CC-BY-4.0"}, "attribution": "Test credit",
             "evidence": [record], "technical": {"duration_s": 60},
             "candidate_segments": [{"start": 5, "end": 25}]}
    return {"schema": "episode-music-catalog/v1", "selection": record, "tracks": [track]}


def test_official_mp3_links_preserve_order_and_remove_duplicates():
    parser = AudioLinks()
    parser.feed('<a href="https://example.test/full.mp3">Full</a><a href="https://example.test/full.mp3">Again</a>'
                '<a href="https://example.test/alternate.mp3">No piano</a><a href="fake.mp4">Video</a>')
    assert parser.links == ["https://example.test/full.mp3", "https://example.test/alternate.mp3"]


def test_verifies_catalog_identity_and_evidence(tmp_path):
    assert verify_catalog(tmp_path, fixture_catalog(tmp_path))["tracks"] == 1


def test_rejects_changed_audio(tmp_path):
    catalog = fixture_catalog(tmp_path)
    catalog["tracks"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_catalog(tmp_path, catalog)


def test_rejects_duplicate_tracks(tmp_path):
    catalog = fixture_catalog(tmp_path)
    catalog["tracks"].append(deepcopy(catalog["tracks"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        verify_catalog(tmp_path, catalog)


def test_rejects_unreviewed_license(tmp_path):
    catalog = fixture_catalog(tmp_path)
    catalog["tracks"][0]["license"]["id"] = "UNKNOWN"
    with pytest.raises(ValueError, match="licensing"):
        verify_catalog(tmp_path, catalog)


def test_rejects_invalid_candidate_segment(tmp_path):
    catalog = fixture_catalog(tmp_path)
    catalog["tracks"][0]["candidate_segments"][0]["end"] = 61
    with pytest.raises(ValueError, match="segment"):
        verify_catalog(tmp_path, catalog)


def test_merge_preserves_all_existing_annotations(tmp_path):
    catalog = fixture_catalog(tmp_path)
    before = deepcopy(catalog)
    new = {"id": "new", "sha256": "f" * 64, "human_note": "not auditioned"}
    merged = merge_entries(catalog, [new], {"path": "new-selection.json"})
    assert catalog == before
    assert merged["tracks"][:-1] == before["tracks"]
    assert merged["tracks"][-1] == new
    assert merged["additional_selections"] == [{"path": "new-selection.json"}]


@pytest.mark.parametrize("field", ["id", "sha256"])
def test_merge_rejects_existing_identity(tmp_path, field):
    catalog = fixture_catalog(tmp_path)
    new = {"id": "new", "sha256": "f" * 64}
    new[field] = catalog["tracks"][0][field]
    with pytest.raises(ValueError, match="duplicate"):
        merge_entries(catalog, [new], {})


def test_merge_rejects_duplicates_within_new_batch(tmp_path):
    new = {"id": "new", "sha256": "f" * 64}
    with pytest.raises(ValueError, match="duplicate"):
        merge_entries(fixture_catalog(tmp_path), [new, new], {})


def test_download_rejects_unreviewed_host_before_network(tmp_path):
    with pytest.raises(ValueError, match="allowlist"):
        download("https://unreviewed.example.test/audio.mp3", tmp_path / "audio.mp3")
