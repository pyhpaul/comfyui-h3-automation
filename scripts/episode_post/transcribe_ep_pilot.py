#!/usr/bin/env python3
"""Collect fresh, hash-bound word timestamps from cached pilot unit videos."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

from faster_whisper import WhisperModel


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    model = WhisperModel("small", device="cpu", compute_type="int8",
                         cpu_threads=4, local_files_only=True)
    paths = [args.source] if args.source.is_file() else sorted(args.source.glob("U*-WENXI/*.mp4"))
    for path in paths:
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        name = path.stem if args.source.is_file() else path.parent.name
        dest = args.out / (name + ".json")
        if dest.exists():
            if json.loads(dest.read_text())["sha256"] != sha:
                raise RuntimeError(f"source changed: {path}")
            continue
        started = time.monotonic()
        segments, info = model.transcribe(
            str(path), language="en", word_timestamps=True,
            vad_filter=True, beam_size=5, condition_on_previous_text=False,
        )
        rows = [{"start": s.start, "end": s.end, "text": s.text.strip(),
                 "no_speech_prob": s.no_speech_prob,
                 "words": [{"start": w.start, "end": w.end,
                            "word": w.word.strip(), "probability": w.probability}
                           for w in (s.words or [])]} for s in segments]
        result = {"source": str(path.resolve()), "sha256": sha,
                  "model": "small", "device": "cpu", "compute_type": "int8",
                  "duration": info.duration, "segments": rows,
                  "elapsed_s": round(time.monotonic() - started, 2)}
        dest.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
