import threading

import pytest

from comfy_orch.av_review.scheduling import run_bounded


def test_fast_completion_fills_slot_before_slow_peer_finishes():
    next_started = threading.Event()
    active = 0
    peak = 0
    lock = threading.Lock()

    def worker(index):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            if index == 0:
                assert next_started.wait(3), "Cohort barrier prevented available slot from being filled"
            if index == 2:
                next_started.set()
            return index
        finally:
            with lock:
                active -= 1

    report = run_bounded(list(range(4)), worker, lambda _: False)
    assert report["results"] == list(range(4))
    assert 1 <= peak <= 2 and not report["unsubmitted"]


def test_circuit_does_not_submit_remaining_work_after_failure_limit():
    called = []
    report = run_bounded(list(range(5)), lambda i: called.append(i) or False,
                         lambda value: not value, max_workers=1)
    assert called == [0, 1]
    assert report["unsubmitted"] == [2, 3, 4] and report["circuit_open"]


def test_invalid_limits_fail_before_submission():
    with pytest.raises(ValueError):
        run_bounded([], lambda x: x, bool, max_workers=0)
