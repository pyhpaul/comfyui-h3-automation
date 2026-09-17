from __future__ import annotations

from comfy_orch.manual_call_pack import suppress_on_screen_chinese_leak


def test_speech_colon_rewritten_to_english_cue():
    src = "他盯着她的手，压着火说：{Put it back.} 双人中景。"
    out = suppress_on_screen_chinese_leak(src)
    assert "说：" not in out
    assert "{Put it back.}" in out
    assert "English" in out
    assert "双人中景" in out


def test_appends_hard_no_chinese_text_rules():
    src = "镜头1：动作。\n无字幕、无水印、无额外人物；无背景音乐。"
    out = suppress_on_screen_chinese_leak(src)
    assert "Never speak Chinese" in out
    assert "on-screen" in out.lower() or "subtitles" in out.lower()
    assert "镜头1：动作。" in out


def test_strips_timing_brackets_that_get_spoken():
    src = "缓推。〔本条最长的一镜，占全条约二分之一〕\n〔一拍即过〕结尾。"
    out = suppress_on_screen_chinese_leak(src)
    assert "本条最长" not in out
    assert "一拍即过" not in out
    assert "〔" not in out and "〕" not in out
    assert "缓推。" in out
    assert "do not narrate" in out.lower() or "stage direction" in out.lower()
