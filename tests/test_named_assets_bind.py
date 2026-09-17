from __future__ import annotations

from comfy_orch.named_assets_bind import (
    drama_label,
    ensure_bind_line,
    motion_latent_prefix,
    refresh_bind_line_labels,
)


def test_drama_label_prefers_latin_name():
    assert drama_label("Liam", "char-001") == "Liam"
    assert drama_label("Gorke（监工）", "char-012") == "Gorke"


def test_drama_label_keeps_chinese_title_not_asset_id():
    assert drama_label("短猎刀", "prop-017") == "短猎刀"
    assert drama_label("黑铅兽栏门", "scene-003") == "黑铅兽栏门"
    assert drama_label("prop-017", "prop-017") == "prop-017"


def test_ensure_bind_injects_for_yanyong_with_drama_labels():
    h3 = "【H3 提示词】\n【参考设定】沿用 U06、短猎刀 @prop-017。\n\n【氛围与画质】x\n"
    entries = [
        ("char-001", "Liam"),
        ("char-012", "Gorke"),
        ("scene-003", "黑铅兽栏门"),
        ("prop-017", "短猎刀"),
    ]
    out, injected = ensure_bind_line(h3, entries)
    assert injected is True
    assert "绑定资产：" in out
    assert "@char-001（Liam）" in out
    assert "@scene-003（黑铅兽栏门）" in out
    assert "@prop-017（短猎刀）" in out
    assert "（prop-017）" not in out
    assert "（scene-003）" not in out


def test_refresh_replaces_id_labels():
    h3 = (
        "【参考设定】沿用 U06。\n"
        "绑定资产：@char-001（Liam）；@scene-003（scene-003）；@prop-017（prop-017）。\n"
    )
    out = refresh_bind_line_labels(
        h3,
        [("char-001", "Liam"), ("scene-003", "黑铅兽栏门"), ("prop-017", "短猎刀")],
    )
    assert "@scene-003（黑铅兽栏门）" in out
    assert "@prop-017（短猎刀）" in out
    assert "（scene-003）" not in out


def test_motion_latent_prefix_from_episode():
    assert motion_latent_prefix("EP04-H3-manual-v16", "U07") == "h3_context/ep04_u07"
    assert motion_latent_prefix("EP05-H3-manual-v19", "U01") == "h3_context/ep05_u01"
    assert motion_latent_prefix("weird", "3") == "h3_context/ep_u03"
