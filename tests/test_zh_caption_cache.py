"""zh_captions map warm / harvest / bootstrap."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "scripts/episode_post"))

from reexport_lihun_edits_v2 import (  # noqa: E402
    _BOOTSTRAP_ZH,
    harvest_zh_from_episode_edits,
    normalize_en,
    warm_zh_map,
)


def test_bootstrap_shorts_seeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty: dict[str, str] = {}
    # Point harvest at empty dir so only bootstrap applies.
    monkeypatch.setattr(
        "reexport_lihun_edits_v2.ROOT",
        tmp_path,
    )
    (tmp_path / "outputs" / "episode-edits" / "lihun-v23").mkdir(parents=True)
    (tmp_path / ".cache" / "lihun_edit_reexport").mkdir(parents=True)
    monkeypatch.setattr(
        "reexport_lihun_edits_v2.ZH_MAP",
        tmp_path / ".cache" / "lihun_edit_reexport" / "zh_captions_map.json",
    )
    warmed = warm_zh_map(empty)
    assert warmed[normalize_en("What?")] == "什么？"
    assert warmed[normalize_en("Whose?")] == "谁的？"
    assert len(warmed) >= len(_BOOTSTRAP_ZH)


def test_harvest_index_aligned_srt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ep = tmp_path / "outputs" / "episode-edits" / "lihun-v23" / "EP99"
    ep.mkdir(parents=True)
    (ep / "EP99.en.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nHello there.\n\n"
        "2\n00:00:01,000 --> 00:00:02,000\nSkip me.\n\n",
        encoding="utf-8",
    )
    (ep / "EP99.zh.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\n你好啊。\n\n"
        "2\n00:00:01,000 --> 00:00:02,000\nSkip me.\n\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("reexport_lihun_edits_v2.ROOT", tmp_path)
    zh_map: dict[str, str] = {}
    added = harvest_zh_from_episode_edits(zh_map)
    assert added == 1
    assert zh_map[normalize_en("Hello there.")] == "你好啊。"
    assert normalize_en("Skip me.") not in zh_map  # English leftover skipped
