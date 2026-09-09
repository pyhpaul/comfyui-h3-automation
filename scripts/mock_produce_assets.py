#!/usr/bin/env python3
"""Mock local asset producer: drop ready job dirs into inbox/ for comfy-orch watch.

Uses templates/smoke_passthrough so CPU ComfyUI can complete the full orch path
(upload → prompt → download). Swap template/fields later for YZ H3 jobs.
"""
from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path


def _png(w: int, h: int, rgb: tuple[int, int, int]) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def produce_one(inbox: Path, name: str, rgb: tuple[int, int, int], prompt: str) -> Path:
    job = inbox / name
    assets = job / "assets"
    assets.mkdir(parents=True, exist_ok=False)
    (assets / "first_frame.png").write_bytes(_png(96, 64, rgb))
    # prompt is recorded for future YZ bindings; smoke template only needs the image
    (job / "job.yaml").write_text(
        f"template: smoke_passthrough\n"
        f"fields:\n"
        f"  first_frame: assets/first_frame.png\n"
        f"  # mock prompt kept for asset-pack shape (ignored by smoke schema)\n"
        f"  # prompt: {prompt!r}\n",
        encoding="utf-8",
    )
    (job / "meta.txt").write_text(f"prompt={prompt}\n", encoding="utf-8")
    return job


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--inbox",
        type=Path,
        default=None,
        help="inbox directory (default: <repo>/inbox)",
    )
    p.add_argument("--count", type=int, default=3, help="how many mock jobs to create")
    args = p.parse_args()

    root = Path(__file__).resolve().parents[1]
    inbox = args.inbox or (root / "inbox")
    inbox.mkdir(parents=True, exist_ok=True)

    palette = [
        ((220, 60, 60), "mock shot A: red character enter room"),
        ((60, 180, 80), "mock shot B: green scene establishing"),
        ((50, 100, 220), "mock shot C: blue product closeup"),
        ((200, 160, 40), "mock shot D: warm dialogue beat"),
        ((160, 80, 200), "mock shot E: purple transition"),
    ]
    created: list[Path] = []
    for i in range(args.count):
        rgb, prompt = palette[i % len(palette)]
        name = f"mock_job_{i + 1:03d}"
        # allow re-run: clear leftover same name in inbox only (not .done)
        target = inbox / name
        if target.exists():
            raise SystemExit(f"refusing to overwrite existing {target}")
        created.append(produce_one(inbox, name, rgb, prompt))

    print(f"produced {len(created)} jobs under {inbox}")
    for c in created:
        print(f"  {c.name}")


if __name__ == "__main__":
    main()
