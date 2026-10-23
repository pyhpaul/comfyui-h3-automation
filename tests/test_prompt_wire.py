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


def test_semantic_warns_picture1_identity_vs_shot1_focus():
    from comfy_orch.prompt_wire import audit_pack_prompt_semantics

    wired = (
        "绑定资产：<Picture 1>（Liam 身份与煤黑风衣母版）；"
        "<Picture 2>（暗影魔龙身份母版）；"
        "<Picture 3>（Alden 身份与潮湿腕甲母版）；"
        "<Picture 4>（暗渠死角空间主图）。\n"
        "人物对白只能读（）内的英文，禁止读旁白。\n"
        "【镜头1｜0–3秒｜极近景／定机】Alden 左手引信跳橘红火星。\n"
        "【镜头2｜3–7秒｜肩后侧中景／缓推】Liam 右掌下压。\n"
    )
    fields = {
        "ref_image_0": "assets/id0-char-001.png",
        "ref_image_1": "assets/id1-char-006.png",
        "ref_image_2": "assets/id2-char-013-agent-alden.png",
        "ref_image_3": "assets/id3-scene-020.png",
    }
    violations, warnings = audit_pack_prompt_semantics(wired, fields)
    assert any("Picture 1" in v and "Alden" in v and "Liam" in v for v in violations)
    assert any("中文" in w or "Chinese" in w for w in warnings)


def test_semantic_call_package_style_picture1_mismatch():
    from comfy_orch.prompt_wire import audit_pack_prompt_semantics

    wired = (
        "- **特工 艾伦（Alden）**：……这是艾伦的角色参考 <Picture 2>\n"
        "- **利亚姆（Liam）**：24岁白人男性，黑发风衣，立于龙背，神纹流淌，冷酷睥睨。"
        "这是利亚姆的角色参考 <Picture 1>\n"
        "【镜头1｜00:00–00:06｜极特写／微距悬停后急推】\n"
        "微距摄影紧锁 Alden 手中剧烈喷射火花的炼金手雷 <Picture 4> 顶部引信。\n"
    )
    fields = {
        "ref_image_0": "assets/id0-char-001.png",
        "ref_image_1": "assets/id1-char-002.png",
        "ref_image_2": "assets/id2-char-003.png",
    }
    violations, _warnings = audit_pack_prompt_semantics(wired, fields)
    assert any("Picture 1" in v and "Liam" in v and "Alden" in v for v in violations)


def test_semantic_clean_when_picture1_matches_shot1_lead():
    from comfy_orch.prompt_wire import audit_pack_prompt_semantics

    wired = (
        "利亚姆（Liam）：这是利亚姆的角色参考 <Picture 1>\n"
        "特工 艾伦（Alden）：这是艾伦的角色参考 <Picture 2>\n"
        "【镜头1｜00:00–00:07｜近景】Liam 合拢账本后吐出台词。\n"
    )
    fields = {
        "ref_image_0": "assets/id0-char-001.png",
        "ref_image_1": "assets/id1-char-002.png",
    }
    violations, warnings = audit_pack_prompt_semantics(wired, fields)
    assert violations == []
    assert not any("focus mismatch" in w for w in warnings)


def test_wire_at_asset_prefix_named_files():
    src = "绑定资产：@char-013（Alden）；@scene-018（哨廊）；@prop-020-v2（罗盘）。保存原始 H3 AV latent\n"
    fields = {
        "ref_image_0": "assets/id0-char-013-agent-alden.png",
        "ref_image_1": "assets/id1-scene-018-sentry-corridor.png",
        "ref_image_2": "assets/id2-prop-020-v2-aether-compass-intact.png",
    }
    wired = wire_pack_prompt(src, fields)
    assert "@char-013" not in wired
    assert "@scene-018" not in wired
    assert "@prop-020-v2" not in wired
    assert "<Picture 1>" in wired and "<Picture 2>" in wired and "<Picture 3>" in wired
    assert "保存原始 H3 AV latent" in wired
    assert audit_pack_prompt_wiring(src, wired, fields) == []


def test_wire_at_asset_tokens_ep07_style():
    src = (
        "这是艾伦的角色参考 @char-002\n"
        "道具参考 @prop-001\n"
        "场景参考 @scene-001\n"
        "镜头里再次点名 @char-002。\n"
        "保存原始 H3 AV latent\n"
    )
    fields = {
        "ref_image_0": "assets/id0-char-002.png",
        "ref_image_1": "assets/id1-prop-001.png",
        "ref_image_2": "assets/id2-scene-001.png",
    }
    wired = wire_pack_prompt(src, fields)
    assert "@char-002" not in wired
    assert "@prop-001" not in wired
    assert "@scene-001" not in wired
    assert wired.count("<Picture 1>") >= 2
    assert "<Picture 2>" in wired and "<Picture 3>" in wired
    assert "保存原始 H3 AV latent" in wired
    assert audit_pack_prompt_wiring(src, wired, fields) == []


def test_wire_ninth_image_slot():
    fields = {f"ref_image_{i}": f"assets/id{i}-char-{i:03d}.png" for i in range(9)}
    src = "\n".join(f"identity @char-{i:03d}" for i in range(9)) + "\n"

    wired = wire_pack_prompt(src, fields)

    assert "<Picture 9>" in wired
    assert "@char-008" not in wired
    assert audit_pack_prompt_wiring(src, wired, fields) == []



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
