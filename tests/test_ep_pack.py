from __future__ import annotations

import json
from pathlib import Path

import yaml

from comfy_orch.ep_pack import (
    build_unit_job,
    map_yz_media_slots,
    parse_prompt_upload_order,
    parse_prompt_duration_seconds,
)


def test_parse_prompt_upload_order():
    text = """header
【本 U 实际上传顺序】
1. assets/characters/char-001.png
2. control/U01-director-control.png
3. previz/U01-colour-blockout.webm

## body
"""
    assert parse_prompt_upload_order(text) == [
        "assets/characters/char-001.png",
        "control/U01-director-control.png",
        "previz/U01-colour-blockout.webm",
    ]


def test_parse_prompt_duration_seconds():
    assert parse_prompt_duration_seconds("## U01｜10 秒｜锁落") == 10
    assert parse_prompt_duration_seconds("## U01 · 坠入毒池（10s）") == 10
    assert parse_prompt_duration_seconds("no duration") is None


def test_map_yz_media_slots_no_pad_and_trims():
    slots = map_yz_media_slots(
        control="control.png",
        previz="previz.webm",
        identities=["a.png", "b.png"],
    )
    assert slots == {
        "ref_image_0": "control.png",
        "ref_image_1": "a.png",
        "ref_image_2": "b.png",
        "ref_video_0": "previz.webm",
    }
    assert "ref_image_3" not in slots

    many = map_yz_media_slots(
        control="c.png",
        previz="v.webm",
        identities=[f"i{i}.png" for i in range(7)],
    )
    assert many["ref_image_1"] == "i0.png"
    assert many["ref_image_5"] == "i4.png"
    assert "ref_image_6" not in many


def _write_tiny(path: Path, payload: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def test_build_unit_job_ep03_style(tmp_path: Path):
    pack = tmp_path / "EP03"
    for rel in [
        "assets/characters/char-001.png",
        "assets/scenes/scene-010.png",
        "control/U01-director-control.png",
        "previz/U01-colour-blockout.webm",
    ]:
        _write_tiny(pack / rel)
    (pack / "prompts").mkdir(parents=True)
    (pack / "prompts" / "U01.txt").write_text("prompt body\n", encoding="utf-8")
    (pack / "upload-manifest.json").write_text(
        json.dumps(
            {
                "units": [
                    {
                        "unit_id": "U01",
                        "duration_seconds": 10,
                        "upload_order": [
                            {"path": "assets/characters/char-001.png"},
                            {"path": "assets/scenes/scene-010.png"},
                            {"path": "control/U01-director-control.png"},
                            {"path": "previz/U01-colour-blockout.webm"},
                        ],
                        "control_reference": {
                            "path": "control/U01-director-control.png",
                        },
                        "previz_reference": {
                            "path": "previz/U01-colour-blockout.webm",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    out = tmp_path / "jobs"
    job_dir = build_unit_job(pack, "U01", out)
    job = yaml.safe_load((job_dir / "job.yaml").read_text(encoding="utf-8"))
    assert job["template"] == "yz_h3_ep_unit"
    assert job["fields"]["duration_seconds"] == 10
    assert "subject_definitions:" in job["fields"]["prompt"]
    assert "non_diegetic_music:" in job["fields"]["prompt"]
    assert (job_dir / "assets" / "prompt_source.txt").read_text(encoding="utf-8") == "prompt body\n"
    assert (job_dir / "assets" / "prompt_h3.txt").read_text(encoding="utf-8") == job["fields"]["prompt"]
    assert job["fields"]["ref_image_0"].endswith("director-control.png")
    assert job["fields"]["ref_video_0"].endswith(".webm")
    assert (job_dir / job["fields"]["ref_image_0"]).is_file()
    assert (job_dir / job["fields"]["ref_video_0"]).is_file()
    assert job["fields"]["ref_image_1"].endswith("char-001.png")
    assert job["fields"]["ref_image_2"].endswith("scene-010.png")
    assert job["fields"]["filename_prefix"] == "EP03-U01"
    assert "ref_image_3" not in job["fields"]
    assert "ref_image_4" not in job["fields"]
    assert "ref_image_5" not in job["fields"]


def test_build_unit_job_ep04_style_from_prompt_order(tmp_path: Path):
    pack = tmp_path / "EP04"
    for rel in [
        "assets/characters/char-001.png",
        "assets/props/prop-015.png",
        "control/U01-director-control.png",
        "previz/U01-colour-blockout.webm",
    ]:
        _write_tiny(pack / rel)
    prompt = """# EP04
【本 U 实际上传顺序】
1. assets/characters/char-001.png
2. assets/props/prop-015.png
3. control/U01-director-control.png
4. previz/U01-colour-blockout.webm

## U01｜10 秒｜锁落
body
"""
    (pack / "prompts").mkdir(parents=True)
    (pack / "prompts" / "U01.txt").write_text(prompt, encoding="utf-8")
    (pack / "upload-manifest.json").write_text(
        json.dumps(
            {
                "units": [
                    {
                        "unit_id": "U01",
                        "control": {"path": "control/U01-director-control.png"},
                        "previz": {"path": "previz/U01-colour-blockout.webm"},
                        "prompt": {"path": "prompts/U01.txt"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    job_dir = build_unit_job(pack, "U01", tmp_path / "jobs")
    job = yaml.safe_load((job_dir / "job.yaml").read_text(encoding="utf-8"))
    assert job["fields"]["duration_seconds"] == 10
    assert job["fields"]["ref_image_1"].endswith("char-001.png")
    assert job["fields"]["ref_image_2"].endswith("prop-015.png")
    assert job["fields"]["ref_image_0"].endswith("director-control.png")
    assert "ref_image_3" not in job["fields"]
