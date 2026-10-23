#!/usr/bin/env python3
"""Extract matched-timestamp stills from before/after FaceRefine mp4s."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


DEFAULT_PCTS = (10, 50, 80)


def probe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "json", str(path),
        ],
        text=True,
        timeout=60,
    )
    data = json.loads(out)
    dur = float((data.get("format") or {}).get("duration") or 0)
    if dur <= 0:
        raise RuntimeError(f"bad duration for {path}")
    return dur


def extract_at(path: Path, seconds: float, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", f"{seconds:.3f}", "-i", str(path),
            "-frames:v", "1", "-q:v", "2", str(dest),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )


def extract_pair(
    before: Path,
    after: Path,
    out_dir: Path,
    pcts: tuple[int, ...] = DEFAULT_PCTS,
) -> list[dict]:
    d0 = probe_duration(before)
    d1 = probe_duration(after)
    # Use the shorter duration so both frames exist.
    dur = min(d0, d1)
    rows: list[dict] = []
    for pct in pcts:
        t = max(0.0, min(dur * (pct / 100.0), max(dur - 0.05, 0.0)))
        b_path = out_dir / "before" / f"t{pct:02d}.png"
        a_path = out_dir / "after" / f"t{pct:02d}.png"
        extract_at(before, t, b_path)
        extract_at(after, t, a_path)
        rows.append({
            "pct": pct,
            "seconds": round(t, 3),
            "before": str(b_path),
            "after": str(a_path),
        })
    manifest = {
        "before_duration_s": round(d0, 3),
        "after_duration_s": round(d1, 3),
        "frames": rows,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", type=Path, required=True)
    ap.add_argument("--after", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pcts", nargs="+", type=int, default=list(DEFAULT_PCTS))
    args = ap.parse_args()
    rows = extract_pair(args.before, args.after, args.out, tuple(args.pcts))
    print(json.dumps({"ok": True, "n": len(rows), "out": str(args.out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
