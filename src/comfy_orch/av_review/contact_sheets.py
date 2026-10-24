"""Timestamped navigation sheets; originals remain authoritative detail evidence."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .frames import Frame
from .media import MediaError


def build_contact_sheets(frames: list[Frame], output: Path, *, prefix: str = "F") -> list[dict]:
    from PIL import Image, ImageDraw, ImageFont

    if not prefix.isascii() or not prefix.isalpha() or len(prefix) > 4:
        raise MediaError("Frame prefix must be 1-4 ASCII letters")
    if not frames or len(frames) > 64:
        raise MediaError("Navigation sheets require 1-64 frames")
    output.mkdir(exist_ok=False)
    font = ImageFont.load_default(size=20)
    sheets = []
    for first in range(0, len(frames), 6):
        selected = frames[first:first+6]
        rows = (len(selected)+1)//2
        sheet = Image.new("RGB", (768, rows*720), "#161616")
        draw = ImageDraw.Draw(sheet)
        cells = []
        for local, frame in enumerate(selected):
            if hashlib.sha256(frame.path.read_bytes()).hexdigest() != frame.sha256:
                raise MediaError("Frame hash changed before navigation sheet generation")
            x, y = (local % 2)*384, (local//2)*720
            with Image.open(frame.path) as image:
                image.thumbnail((384, 688))
                sheet.paste(image, (x+(384-image.width)//2, y+32))
            frame_id = f"{prefix}{first+local+1:03d}"
            draw.text((x+8, y+5), f"{frame_id}  {frame.time:.3f}s", font=font, fill="white")
            cells.append({"frame_id": frame_id, "source_time": frame.time,
                          "frame_path": str(frame.path), "frame_sha256": frame.sha256})
        path = output / f"sheet-{len(sheets)+1:02d}.jpg"
        with path.open("xb") as handle:
            sheet.save(handle, "JPEG", quality=90)
        sheets.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                       "width": sheet.width, "height": sheet.height, "cells": cells})
    return sheets
