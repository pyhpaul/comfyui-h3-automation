from __future__ import annotations

from pathlib import Path

from comfy_orch.ep_pack import build_unit_job
from comfy_orch.prompt_wire import audit_pack_prompt_wiring, wire_pack_prompt

PACK = Path("/tmp/EP02-H3-physical-causality-test-v2_1-20260910")


def test_wire_replaces_windows_paths_only():
    src = (PACK / "ep02/prompts/U02.txt").read_text(encoding="utf-8")
    fields = {
        "ref_image_0": "assets/id0-char-001.png",
        "ref_image_1": "assets/id1-char-003-v5.png",
        "ref_image_2": "assets/id2-char-011-corrupted-lurker.png",
        "ref_image_3": "assets/id3-scene-007.png",
    }
    wired = wire_pack_prompt(src, fields)
    assert "<Picture 1>" in wired and "<Picture 4>" in wired
    assert "char-001.png" not in wired
    assert "E:\\" not in wired and "E:/" not in wired
    assert "Vance 的单一反击" in wired or "斩开兽首" in wired
    assert audit_pack_prompt_wiring(src, wired, fields) == []


def test_parent_video_injects_label_without_rewriting_save_rule():
    src = (PACK / "ep02/prompts/U02.txt").read_text(encoding="utf-8")
    fields = {
        "ref_image_0": "assets/id0-char-001.png",
        "ref_image_1": "assets/id1-char-003-v5.png",
        "ref_image_2": "assets/id2-char-011-corrupted-lurker.png",
        "ref_image_3": "assets/id3-scene-007.png",
        "ref_video_0": "assets/parent_prev.mp4",
    }
    wired = wire_pack_prompt(src, fields)
    assert "父片段：<Video 1>" in wired
    assert "保存原始 H3 AV latent" in wired
    assert "保存<Video 1>" not in wired
    assert audit_pack_prompt_wiring(src, wired, fields) == []


def test_preflight_job_dir_covers_parent_path(tmp_path: Path):
    from comfy_orch.prompt_wire import preflight_job_dir

    job = build_unit_job(PACK, "U02", tmp_path)
    rep = preflight_job_dir(job, require_parent_path=True)
    assert rep["ok"] is True
    assert rep["no_parent"]["ok"] is True
    assert rep["with_parent"]["ok"] is True
    assert rep["with_parent"]["has_video_label"] is True


def test_preflight_all_ep02_built_jobs():
    from comfy_orch.prompt_wire import preflight_job_dir

    root = Path(__file__).resolve().parents[1]
    jobs = sorted(
        (root / "jobs" / "ep_units").glob(
            "EP02-H3-physical-causality-test-v2_1-20260910-U*"
        )
    )
    assert len(jobs) >= 7
    for job in jobs:
        rep = preflight_job_dir(job, require_parent_path=True)
        assert rep["ok"], (job.name, rep)


def test_audit_rejects_body_edits():
    src = "hello 角色\nassets/characters/char-001.png\n"
    fields = {"ref_image_0": "assets/id0-char-001.png"}
    wired = wire_pack_prompt(src, fields)
    bad = wired.replace("角色", "改了")
    assert audit_pack_prompt_wiring(src, bad, fields)


def test_build_u01_keeps_chinese_body(tmp_path: Path):
    job = build_unit_job(PACK, "U01", tmp_path)
    prompt = (job / "assets" / "prompt_h3.txt").read_text(encoding="utf-8")
    source = (job / "assets" / "prompt_source.txt").read_text(encoding="utf-8")
    assert "诱兽粉" in prompt or "踩粉" in prompt
    assert "<Picture 1>" in prompt
    assert "subject_definitions:" not in prompt
    assert (job / "assets" / "prompt_audit.json").is_file()
    assert audit_pack_prompt_wiring(
        source,
        prompt,
        {
            k: v
            for k, v in __import__("yaml")
            .safe_load((job / "job.yaml").read_text())["fields"]
            .items()
            if k.startswith("ref_")
        },
    ) == []
