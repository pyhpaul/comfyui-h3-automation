"""Frame extract helper for FaceRefine A/B stills."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
import facerefine_extract_frames as extract  # noqa: E402


def _tiny_mp4(path: Path, color: str, seconds: float = 1.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            f"color=c={color}:s=64x64:d={seconds}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )


def test_extract_pair_writes_matched_pct_pngs(tmp_path):
    before = tmp_path / "before.mp4"
    after = tmp_path / "after.mp4"
    _tiny_mp4(before, "red", 1.0)
    _tiny_mp4(after, "blue", 1.0)
    out = tmp_path / "frames"
    rows = extract.extract_pair(before, after, out, pcts=(10, 50, 80))
    assert len(rows) == 3
    for row in rows:
        assert Path(row["before"]).is_file()
        assert Path(row["after"]).is_file()
        assert Path(row["before"]).stat().st_size > 0
    assert (out / "manifest.json").is_file()
