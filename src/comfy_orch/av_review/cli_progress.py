"""Local receipt timing only; do not persist reasoning text or command arguments."""
from __future__ import annotations

import json
from pathlib import Path
import threading
import time


class ReceiptProgress:
    def __init__(self, expected: set[str]):
        self.expected = expected
        self.read = set()
        self.milestones = {}
        self.invalid_lines = 0

    def observe(self, event: dict, elapsed: float) -> bool:
        before = (len(self.read), len(self.milestones))
        self.milestones.setdefault("first_event_seconds", round(elapsed, 3))
        if event.get("type") == "result":
            self.milestones.setdefault("final_receipt_seconds", round(elapsed, 3))
        tool = _nested_object(event, ("tool_call", "readToolCall"))
        success = _nested_object(tool, ("result", "success"))
        if event.get("subtype") == "completed" and success.get("dataBlobId"):
            raw_path = _nested_object(tool, ("args",)).get("path", "")
            path = str(Path(raw_path).resolve()) if isinstance(raw_path, str) else ""
            if path in self.expected:
                self.read.add(path)
                self.milestones.setdefault("first_image_seconds", round(elapsed, 3))
                if self.read == self.expected:
                    self.milestones.setdefault("all_images_seconds", round(elapsed, 3))
        return before != (len(self.read), len(self.milestones))

    def summary(self) -> dict:
        if not self.milestones:
            phase = "NO_STDOUT_EVENT"
        elif "final_receipt_seconds" in self.milestones:
            phase = "FINAL_RECEIPT_NOT_YET_VALIDATED"
        elif not self.read:
            phase = "EVENTS_WITHOUT_IMAGE_RECEIPTS"
        elif self.read != self.expected:
            phase = "PARTIAL_IMAGE_RECEIPTS_NO_FINAL"
        else:
            phase = "ALL_IMAGE_RECEIPTS_NO_FINAL"
        return {"phase": phase, "timing": dict(self.milestones), "image_receipts": len(self.read),
                "invalid_lines": self.invalid_lines, "timing_basis": "LOCAL_RECEIPT_NOT_PROVIDER_LATENCY"}


def _nested_object(data: dict, keys: tuple[str, ...]) -> dict:
    for key in keys:
        data = data.get(key)
        if not isinstance(data, dict):
            return {}
    return data


class CaptureProgress:
    def __init__(self, directory: Path, expected: set[str], started: float):
        self.directory = directory
        self.started = started
        self.recorder = ReceiptProgress(expected)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._capture, daemon=True)

    def _capture(self):
        pending = b""
        with (self.directory / "raw.jsonl").open("rb") as source, \
                (self.directory / "progress.jsonl").open("x", encoding="utf-8") as output:
            while True:
                pending += source.read()
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    try:
                        event = json.loads(line)
                    except ValueError:
                        self.recorder.invalid_lines += 1
                        continue
                    if not isinstance(event, dict):
                        self.recorder.invalid_lines += 1
                        continue
                    if self.recorder.observe(event, time.monotonic()-self.started):
                        output.write(json.dumps(self.recorder.summary())+"\n")
                        output.flush()
                if self.stop.wait(0.1):
                    # One last read collects bytes flushed just before process exit.
                    pending += source.read()
                    for line in pending.splitlines():
                        try:
                            event = json.loads(line)
                        except ValueError:
                            self.recorder.invalid_lines += 1
                            continue
                        if isinstance(event, dict):
                            self.recorder.observe(event, time.monotonic()-self.started)
                    output.write(json.dumps(self.recorder.summary())+"\n")
                    output.flush()
                    break

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join()
