import json
from pathlib import Path
import time

from comfy_orch.av_review.cli_progress import CaptureProgress, ReceiptProgress


def image_event(path):
    return {"type": "tool_call", "subtype": "completed", "tool_call": {"readToolCall": {
        "args": {"path": str(path)}, "result": {"success": {"dataBlobId": "image"}}}}}


def test_receipt_stages_do_not_confuse_silent_timeout_with_model_inference():
    path = str(Path("a.jpg").resolve())
    recorder = ReceiptProgress({path})
    assert recorder.summary()["phase"] == "NO_STDOUT_EVENT"
    recorder.observe({"type": "system"}, 2)
    assert recorder.summary()["phase"] == "EVENTS_WITHOUT_IMAGE_RECEIPTS"
    recorder.observe(image_event(path), 5)
    assert recorder.summary()["phase"] == "ALL_IMAGE_RECEIPTS_NO_FINAL"
    recorder.observe({"type": "result"}, 8)
    assert recorder.summary()["timing"] == {"first_event_seconds": 2,
        "first_image_seconds": 5, "all_images_seconds": 5, "final_receipt_seconds": 8}


def test_partial_unknown_duplicate_and_unconfirmed_reads():
    paths = {str(Path(p).resolve()) for p in ["a.jpg", "b.jpg"]}
    recorder = ReceiptProgress(paths)
    recorder.observe(image_event("a.jpg"), 2)
    recorder.observe(image_event("a.jpg"), 3)
    recorder.observe(image_event("c.jpg"), 4)
    assert recorder.summary()["image_receipts"] == 1
    assert recorder.summary()["phase"] == "PARTIAL_IMAGE_RECEIPTS_NO_FINAL"


def test_malformed_metadata_is_not_an_image_receipt():
    recorder = ReceiptProgress({"a.jpg"})
    for event in [{"tool_call": None}, {"tool_call": {"readToolCall": "invalid"}},
                  {"tool_call": {"readToolCall": {"result": {"success": None}}}}]:
        recorder.observe(event, 1)
    assert recorder.summary()["image_receipts"] == 0


def test_capture_joins_reads_final_flush_and_never_copies_event_text(tmp_path):
    raw = tmp_path / "raw.jsonl"
    raw.touch()
    with CaptureProgress(tmp_path, set(), time.monotonic()) as capture:
        with raw.open("a") as handle:
            handle.write(json.dumps({"type": "system", "text": "private content"})+"\n")
            handle.write(json.dumps({"type": "result"})+"\n")
    assert capture.recorder.summary()["phase"] == "FINAL_RECEIPT_NOT_YET_VALIDATED"
    assert not capture.thread.is_alive()
    assert "private content" not in (tmp_path / "progress.jsonl").read_text()


def test_capture_accepts_utf8_split_across_reads_and_records_invalid_lines(tmp_path):
    raw = tmp_path / "raw.jsonl"
    raw.touch()
    record = json.dumps({"type": "system", "text": "中文"}, ensure_ascii=False).encode()+b"\n"
    split = record.index("中".encode())+1
    with CaptureProgress(tmp_path, set(), time.monotonic()) as capture:
        with raw.open("ab", buffering=0) as handle:
            handle.write(record[:split])
            time.sleep(0.15)
            handle.write(record[split:]+b"not-json\n")
    assert capture.recorder.summary()["invalid_lines"] == 1
    assert capture.recorder.summary()["phase"] == "EVENTS_WITHOUT_IMAGE_RECEIPTS"
