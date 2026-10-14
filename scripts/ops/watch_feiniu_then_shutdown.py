#!/usr/bin/env python3
"""After a Feiniu queue, shut the Chenyu pod down without another reminder.

Start this in its own process when the user has asked to shut down after the
batch. It waits for the runner pid, then refuses to click 关机 unless the log
is a clean BATCH_DONE, every planned unit has the four archive files, and
Comfy /queue is empty.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path


def archive_complete(names: list[str]) -> bool:
    return (
        any(name.endswith(".mp4") for name in names)
        and any(name.endswith(".safetensors") for name in names)
        and "prompt_h3.txt" in names
        and "run_meta.json" in names
    )


def hold_reason(
    *,
    exit_marker: str,
    log_text: str,
    archives: dict[str, list[str]],
    queue_running: int,
    queue_pending: int,
) -> str | None:
    """None means the pod may be shut down. Any other string is a hold."""
    if not archives:
        return "no units"
    if f"{exit_marker}:0" not in log_text:
        return "runner exit"
    if "ARCHIVE_FAILED" in log_text or "BATCH_DONE" not in log_text:
        return "runner log"
    missing = [unit for unit, names in archives.items() if not archive_complete(names)]
    if missing:
        return "feiniu " + ",".join(missing)
    if queue_running or queue_pending:
        return f"queue run={queue_running} pend={queue_pending}"
    return None


def _alive(pid: int) -> bool:
    return Path(f"/proc/{pid}").exists()


def _queue_counts(base_url: str) -> tuple[int, int]:
    with urllib.request.urlopen(base_url.rstrip("/") + "/queue", timeout=20) as response:
        payload = json.load(response)
    return len(payload.get("queue_running") or []), len(payload.get("queue_pending") or [])


def _feiniu_names(batch: str, episode: str, units: list[str]) -> dict[str, list[str]]:
    from comfy_orch.feiniu_archive import SHARE, connect_feiniu, remote_unit_dir

    smb = connect_feiniu()
    found: dict[str, list[str]] = {}
    try:
        for unit in units:
            directory = remote_unit_dir(batch, episode, unit)
            names: list[str] = []
            for item in smb.listPath(SHARE, directory + "\\*"):
                name = item.get_longname()
                if name in {".", ".."} or item.is_directory():
                    continue
                names.append(name)
            found[unit] = names
    finally:
        smb.close()
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True, help="Runner shell pid to wait for")
    parser.add_argument("--log", type=Path, required=True, help="Runner log that contains the exit marker")
    parser.add_argument("--exit-marker", required=True, help="Shell echo prefix, matched as MARKER:0")
    parser.add_argument("--ssh-host", required=True)
    parser.add_argument("--feiniu-batch", required=True)
    parser.add_argument("--episode", required=True, help="Episode string containing EP01, EP02, ...")
    parser.add_argument("--units", nargs="+", required=True)
    parser.add_argument("--base-url", default="http://192.168.50.106:8190")
    parser.add_argument("--poll-seconds", type=float, default=20)
    args = parser.parse_args(argv)

    print(f"WATCH pid {args.pid}", flush=True)
    while _alive(args.pid):
        time.sleep(args.poll_seconds)
    print("RUNNER_EXIT", flush=True)
    time.sleep(2)
    log_text = args.log.read_text(encoding="utf-8", errors="replace")
    archives = _feiniu_names(args.feiniu_batch, args.episode, list(args.units))
    running, pending = _queue_counts(args.base_url)
    reason = hold_reason(
        exit_marker=args.exit_marker,
        log_text=log_text,
        archives=archives,
        queue_running=running,
        queue_pending=pending,
    )
    if reason:
        print(f"HOLD {reason}", flush=True)
        return 2
    for unit in args.units:
        print(f"FEINIU_OK {unit}", flush=True)
    print("QUEUE_EMPTY", flush=True)

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from chenyu_shutdown import shutdown_open_pod

    print(shutdown_open_pod(args.ssh_host), flush=True)
    print("SHUTDOWN_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
