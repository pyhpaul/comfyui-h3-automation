from __future__ import annotations

from pathlib import Path

from comfy_orch.ep_pack import build_unit_job, list_unit_ids, map_yz_media_slots
from comfy_orch.latent_pack import (
    is_h3_latent_pack,
    parse_latent_asset_paths,
    parse_latent_sections,
)


PACK = Path("/tmp/EP01-H3-latent-test-package-v1")


def test_is_h3_latent_pack():
    assert is_h3_latent_pack(PACK)


def test_parse_latent_u01_assets_and_duration():
    text = (PACK / "prompts" / "U01_拔管与抓腕.txt").read_text(encoding="utf-8")
    paths = parse_latent_asset_paths(text)
    assert paths[0].endswith("images/characters/char-001.png")
    assert any("char-010" in p for p in paths)
    assert any("prop-011" in p for p in paths)
    sec = parse_latent_sections(text)
    assert int(sec["duration_seconds"]) == 13
    assert "Put it back" in sec["body"]


def test_map_latent_slots_fill_from_zero():
    slots = map_yz_media_slots(
        control=None,
        previz=None,
        identities=["a.png", "b.png", "c.png"],
    )
    assert slots == {
        "ref_image_0": "a.png",
        "ref_image_1": "b.png",
        "ref_image_2": "c.png",
    }
    assert "ref_video_0" not in slots


def test_build_latent_u01_job(tmp_path: Path):
    assert "U01" in list_unit_ids(PACK)
    job = build_unit_job(PACK, "U01", tmp_path)
    import yaml

    data = yaml.safe_load((job / "job.yaml").read_text(encoding="utf-8"))
    assert data["pack_kind"] == "h3_latent"
    assert data["fields"]["duration_seconds"] == 13
    assert "ref_video_0" not in data["fields"]
    assert data["fields"]["ref_image_0"].endswith("char-001.png")
    assert data["fields"]["filename_prefix"] == "EP01-U01"
    prompt = data["fields"]["prompt"]
    assert prompt.startswith("subject_definitions:")
    assert "<Picture 1>" in prompt and "<Subject 1>" in prompt
    assert "E:\\" not in prompt and "assets/" not in prompt
