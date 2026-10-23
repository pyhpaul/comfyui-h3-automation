#!/usr/bin/env python3
"""Wait for queue_lihun_fix_gpu_slice to finish cleanly, then shut Chenyu.

Unlike watch_feiniu_then_shutdown (BATCH_DONE + EXIT:0), this matches
GPU_SLICE_DONE ok=N fail=0, checks /queue empty, spot-checks Feiniu for
the listed candidate unit folders, then clicks 关机.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def alive(pid: int) -> bool:
    return Path(f"/proc/{pid}").exists()


def queue_counts(base: str) -> tuple[int, int]:
    with urllib.request.urlopen(base.rstrip("/") + "/queue", timeout=20) as resp:
        payload = json.load(resp)
    return len(payload.get("queue_running") or []), len(payload.get("queue_pending") or [])


def archive_ok(names: list[str]) -> bool:
    return (
        any(n.endswith(".mp4") for n in names)
        and any(n.endswith(".safetensors") for n in names)
        and "prompt_h3.txt" in names
        and "run_meta.json" in names
    )


def feiniu_unit_names(batch: str, episode: str, unit: str) -> list[str]:
    from comfy_orch.feiniu_archive import SHARE, connect_feiniu, remote_unit_dir

    smb = connect_feiniu()
    try:
        directory = remote_unit_dir(batch, episode, unit)
        out: list[str] = []
        for item in smb.listPath(SHARE, directory + "\\*"):
            name = item.get_longname()
            if name in {".", ".."} or item.is_directory():
                continue
            out.append(name)
        return out
    finally:
        smb.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--log", type=Path, required=True,
                    help="stdout/log containing GPU_SLICE_DONE")
    ap.add_argument("--ssh-host", required=True)
    ap.add_argument("--feiniu-batch", required=True)
    ap.add_argument("--units", nargs="+", required=True,
                    help="candidate tags e.g. EP40-U01C1 EP40-U01C2")
    ap.add_argument("--base-url", default="http://192.168.50.106:8190")
    ap.add_argument("--poll-seconds", type=float, default=20)
    args = ap.parse_args()

    print(f"WATCH_GPU_SLICE pid={args.pid}", flush=True)
    while alive(args.pid):
        time.sleep(args.poll_seconds)
    print("RUNNER_EXIT", flush=True)
    time.sleep(3)

    text = args.log.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"GPU_SLICE_DONE ok=(\d+) fail=(\d+)", text)
    if not m:
        print("HOLD no GPU_SLICE_DONE", flush=True)
        return 2
    ok, fail = int(m.group(1)), int(m.group(2))
    if fail:
        print(f"HOLD GPU_SLICE_DONE fail={fail}", flush=True)
        return 2
    print(f"SLICE_OK ok={ok} fail={fail}", flush=True)

    running, pending = queue_counts(args.base_url)
    if running or pending:
        print(f"HOLD queue run={running} pend={pending}", flush=True)
        return 2
    print("QUEUE_EMPTY", flush=True)

    missing = []
    for tag in args.units:
        ep = tag.split("-")[0]
        try:
            names = feiniu_unit_names(args.feiniu_batch, ep, tag)
        except Exception as exc:
            print(f"HOLD feiniu {tag}: {exc}", flush=True)
            return 2
        if not archive_ok(names):
            missing.append(tag)
        else:
            print(f"FEINIU_OK {tag}", flush=True)
    if missing:
        print("HOLD feiniu " + ",".join(missing), flush=True)
        return 2

    from chenyu_shutdown import shutdown_open_pod
    print(shutdown_open_pod(args.ssh_host), flush=True)
    print("SHUTDOWN_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
