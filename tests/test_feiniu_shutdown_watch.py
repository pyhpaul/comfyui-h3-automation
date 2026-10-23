"""Shutdown waits for a clean Feiniu archive and an empty queue."""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
from watch_feiniu_then_shutdown import archive_complete, hold_reason


def _files() -> dict[str, list[str]]:
    return {
        "U01": ["a.mp4", "a.safetensors", "prompt_h3.txt", "run_meta.json"],
    }


def test_four_archive_files_are_required():
    assert archive_complete(_files()["U01"])
    assert not archive_complete(["a.mp4", "prompt_h3.txt", "run_meta.json"])


def test_clean_batch_may_shut_down():
    log = "BATCH_DONE ok=1 dest=batch\nEP01_EXIT:0\n"
    assert hold_reason(
        exit_marker="EP01_EXIT",
        log_text=log,
        archives=_files(),
        queue_running=0,
        queue_pending=0,
    ) is None


def test_archive_failure_holds():
    log = "ARCHIVE_FAILED upload\nBATCH_DONE ok=1\nEP01_EXIT:0\n"
    assert hold_reason(
        exit_marker="EP01_EXIT",
        log_text=log,
        archives=_files(),
        queue_running=0,
        queue_pending=0,
    ) == "runner log"


def test_nonzero_exit_holds():
    assert (
        hold_reason(
            exit_marker="EP01_EXIT",
            log_text="BATCH_DONE ok=0\nEP01_EXIT:2\n",
            archives=_files(),
            queue_running=0,
            queue_pending=0,
        )
        == "runner exit"
    )


def test_missing_feiniu_file_holds():
    reason = hold_reason(
        exit_marker="EP01_EXIT",
        log_text="BATCH_DONE ok=1\nEP01_EXIT:0\n",
        archives={"U01": ["a.mp4"]},
        queue_running=0,
        queue_pending=0,
    )
    assert reason == "feiniu U01"


def test_busy_queue_holds():
    reason = hold_reason(
        exit_marker="EP01_EXIT",
        log_text="BATCH_DONE ok=1\nEP01_EXIT:0\n",
        archives=_files(),
        queue_running=1,
        queue_pending=0,
    )
    assert reason is not None
    assert reason.startswith("queue")
