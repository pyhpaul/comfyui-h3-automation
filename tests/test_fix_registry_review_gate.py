"""Fix-round verdicts require a complete human dialogue review.

Regression guard for the 2026-10-21 speaker-attribution audit failure:
ASR plus sparse still frames produced two false STRICT verdicts. The
registry must not record strict/relaxed without full-watch evidence, and
a later FAIL must move the slot back to pending.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "scripts/ops/fix_registry.py"
AUDIT = ROOT / "scripts/ops/audit_candidate.py"


def _registry(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REGISTRY), "--registry", str(tmp_path / "r.json"),
         *args],
        text=True, capture_output=True, check=False,
    )


def _seed_registry(tmp_path: Path) -> Path:
    assert _registry(tmp_path, "init", "--units", "EP01-U06").returncode == 0
    assert _registry(
        tmp_path, "add", "--unit", "EP01-U06", "--chain", "wenxi",
        "--tag", "seed2", "--seed", "123",
    ).returncode == 0
    return tmp_path / "r.json"


def test_strict_verdict_requires_full_watch_review_record(tmp_path: Path):
    path = _seed_registry(tmp_path)

    blocked = _registry(
        tmp_path, "verdict", "--unit", "EP01-U06", "--chain", "wenxi",
        "--tag", "seed2", "--verdict", "strict",
    )
    assert blocked.returncode != 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["candidates"][0]["verdict"] == ""
    assert data["slots"]["EP01-U06:wenxi"] == "pending"

    accepted = _registry(
        tmp_path, "verdict", "--unit", "EP01-U06", "--chain", "wenxi",
        "--tag", "seed2", "--verdict", "strict",
        "--review-method", "full-dialogue-watch",
        "--reviewer", "lai",
        "--review-scope", "all-dialogue-lines",
        "--review-evidence", "watched EP01-U06-seed2.mp4 end to end; "
                              "each scripted line checked against mouth owner",
    )
    assert accepted.returncode == 0, accepted.stderr
    data = json.loads(path.read_text(encoding="utf-8"))
    review = data["candidates"][0]["review"]
    assert review["method"] == "full-dialogue-watch"
    assert review["reviewer"] == "lai"
    assert review["scope"] == "all-dialogue-lines"
    assert "mouth owner" in review["evidence"]
    assert data["slots"]["EP01-U06:wenxi"] == "shipped-strict"


def test_failed_verdict_returns_slot_to_pending(tmp_path: Path):
    path = _seed_registry(tmp_path)
    assert _registry(
        tmp_path, "verdict", "--unit", "EP01-U06", "--chain", "wenxi",
        "--tag", "seed2", "--verdict", "strict",
        "--review-method", "full-dialogue-watch",
        "--reviewer", "lai",
        "--review-scope", "all-dialogue-lines",
        "--review-evidence", "complete watch recorded",
    ).returncode == 0

    rejected = _registry(
        tmp_path, "verdict", "--unit", "EP01-U06", "--chain", "wenxi",
        "--tag", "seed2", "--verdict", "fail",
        "--cut", "human rewatch rejected the candidate",
    )
    assert rejected.returncode == 0, rejected.stderr
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["candidates"][0]["verdict"] == "fail"
    assert data["slots"]["EP01-U06:wenxi"] == "pending"


def _load_audit_module():
    spec = importlib.util.spec_from_file_location("audit_candidate", AUDIT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_review_frame_times_cover_whole_dialogue_segment():
    audit = _load_audit_module()
    times = audit.review_frame_times(1.0, 2.02, step=0.25)
    assert times[0] == 1.0
    assert times[-1] == 2.02
    assert all(b - a <= 0.251 for a, b in zip(times, times[1:]))


def test_word_timestamps_group_into_review_segments_on_silence():
    audit = _load_audit_module()
    words = [
        {"start": 0.0, "end": 0.3, "word": "Wade."},
        {"start": 0.4, "end": 0.8, "word": "I"},
        {"start": 0.9, "end": 1.2, "word": "mean"},
        {"start": 2.4, "end": 2.8, "word": "When"},
        {"start": 2.9, "end": 3.2, "word": "have"},
    ]
    segments = audit.group_word_segments(words)
    assert segments == [
        {"start": 0.0, "end": 1.2, "text": "Wade. I mean"},
        {"start": 2.4, "end": 3.2, "text": "When have"},
    ]


def test_human_review_checklist_starts_unreviewed_and_blocks_verdict():
    audit = _load_audit_module()
    review = audit.build_human_review(
        unit="EP01-U06",
        mp4_name="candidate.mp4",
        segments=[{"start": 0.0, "end": 1.6, "text": "Wade. I mean it."}],
        expected_lines=["Wade. I mean it."],
    )
    assert review["status"] == "REQUIRED_NOT_DONE"
    assert review["may_issue_verdict"] is False
    assert review["method_required"] == "full-dialogue-watch"
    assert review["lines"][0]["status"] == "UNREVIEWED"
    assert review["lines"][0]["expected_text"] == "Wade. I mean it."
    assert set(review["lines"][0]["checks"]) == {
        "expected_speaker", "mouth_owner", "other_visible_mouths",
        "line_complete", "line_order",
    }
