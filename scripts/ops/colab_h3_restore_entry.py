"""Formal restore routing: four workers by default, explicit serial rollback."""

from __future__ import annotations

import os
from functools import partial

import colab_h3_restore as base
import colab_h3_restore_fast as fast


def main() -> None:
    value = os.environ.get("H3_RESTORE_WORKERS", "4")
    if value not in {"1", "4"}:
        raise ValueError("H3_RESTORE_WORKERS must be 1 (serial) or 4 (parallel)")
    workers = int(value)
    callback = (base.restore_split_model if workers == 1 else
                partial(fast.restore_split_model, options=fast.RestoreOptions(workers)))
    print(f"RESTORE_MODE workers={workers}", flush=True)
    base.main(restore_model=callback)


if __name__ == "__main__":
    main()
