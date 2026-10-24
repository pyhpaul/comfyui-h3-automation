"""Bounded in-flight work with failure accounting before replacement submission."""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait


def run_bounded(items, worker, is_failure, *, max_workers=2, failure_limit=2):
    if max_workers < 1 or failure_limit < 1:
        raise ValueError("Worker and failure limits must be positive")
    pending = {}
    results = {}
    next_index = 0
    failures = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        while next_index < len(items) or pending:
            while failures < failure_limit and next_index < len(items) and len(pending) < max_workers:
                future = pool.submit(worker, items[next_index])
                pending[future] = next_index
                next_index += 1
            if not pending:
                break
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            # Account for the whole observed completion set before replacing jobs.
            for future in done:
                index = pending.pop(future)
                result = future.result()
                results[index] = result
                failures += bool(is_failure(result))
    return {"results": [results[i] for i in sorted(results)],
            "submitted_count": next_index, "failure_count": failures,
            "unsubmitted": items[next_index:], "circuit_open": failures >= failure_limit}
