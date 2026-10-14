from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from comfy_orch.latent_scene import audit_job_dirs, scene_families_from_fields


def _job(tmp: Path, episode: str, unit: str, refs: dict[str, str]) -> Path:
    job = tmp / f"{episode}-{unit}"
    (job / "assets").mkdir(parents=True)
    (job / "job.yaml").write_text(
        yaml.safe_dump(
            {
                "episode": episode,
                "unit_id": unit,
                "fields": refs,
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return job


def test_same_place_keeps_latent_across_time_of_day(tmp_path: Path):
    episode = "EP-shop"
    jobs = [
        _job(tmp_path, episode, "U01", {"ref_image_0": "assets/id0-scene-004-s01.png"}),
        _job(tmp_path, episode, "U02", {"ref_image_2": "assets/id2-scene-004-s03.png"}),
    ]
    assert audit_job_dirs(jobs) == []


def test_independent_start_already_breaks_the_chain(tmp_path: Path):
    episode = "EP-cut"
    jobs = [
        _job(tmp_path, episode, "U01", {"ref_image_0": "assets/id0-scene-001-s01.png"}),
        _job(tmp_path, episode, "U02", {"ref_image_1": "assets/id1-scene-002-s01.png"}),
    ]
    raw = yaml.safe_load((jobs[1] / "job.yaml").read_text(encoding="utf-8"))
    raw["start_mode"] = "independent"
    (jobs[1] / "job.yaml").write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    assert audit_job_dirs(jobs) == []


def test_scene_change_blocks_motion_latent(tmp_path: Path):
    episode = "EP-cut"
    jobs = [
        _job(tmp_path, episode, "U05", {"ref_image_2": "assets/id2-scene-006-s01.png"}),
        _job(tmp_path, episode, "U06", {"ref_image_6": "assets/id6-scene-004-s03.png"}),
    ]
    violations = audit_job_dirs(jobs)
    assert len(violations) == 1
    assert "U06" in violations[0] and "U05" in violations[0]
    assert "scene-004" in violations[0] and "scene-006" in violations[0]


def test_shared_scene_still_links_when_extra_plate_is_bound(tmp_path: Path):
    episode = "EP-phone"
    jobs = [
        _job(tmp_path, episode, "U03", {"ref_image_4": "assets/id4-scene-002-s02.png"}),
        _job(
            tmp_path,
            episode,
            "U04",
            {
                "ref_image_5": "assets/id5-scene-002-s02.png",
                "ref_image_6": "assets/id6-scene-005-s01.png",
            },
        ),
    ]
    assert audit_job_dirs(jobs) == []


def test_prompt_mention_of_old_scene_does_not_count(tmp_path: Path):
    families = scene_families_from_fields(
        {
            "ref_image_2": "assets/id2-scene-005-s01.png",
            "prompt": "承接 scene-004 小屋，然后硬切",
        }
    )
    assert families == {5}


def test_ep03_scrapyard_to_shop_is_blocked():
    root = Path("jobs/ep_units")
    u05 = root / "EP03-抢Vance钱-v2-U05"
    u06 = root / "EP03-抢Vance钱-v2-U06"
    if not (u05 / "job.yaml").is_file() or not (u06 / "job.yaml").is_file():
        pytest.skip("EP03 v2 jobs are not on disk")
    violations = audit_job_dirs([u05, u06])
    assert len(violations) == 1
    assert "scene-006" in violations[0] and "scene-004" in violations[0]
