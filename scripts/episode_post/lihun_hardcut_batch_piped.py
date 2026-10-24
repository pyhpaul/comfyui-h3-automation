#!/usr/bin/env python3
"""Hard-cut lihun EPs with piped Feiniu archive (v3: up to 2 archives in flight).

Stage → render → background archive; next EP stage+render overlaps uploads.
Same-episode master/review dual-put lives in ``lihun_plan_render_archive.py``.

  PYTHONPATH=src .worktrees/feat-orch/.venv/bin/python -u \\
    scripts/episode_post/lihun_hardcut_batch_piped.py EP43 EP45
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PLAN = ROOT / "runs/lihun_v23_edit_plan.md"
VENV_PY = ROOT / ".worktrees/feat-orch/.venv/bin/python"
STAGE_PY = HERE / "lihun_stage_asr.py"
RENDER_PY = HERE / "lihun_plan_render_archive.py"

# Max concurrent episode archives. 2 removes the common 3–5 min
# WAIT archive_before_put after next render finishes; still caps SMB writers.
MAX_ARCH_IN_FLIGHT = 2

# Historical hard-cut remainder (already done Oct 2026); pass EPs on CLI for new runs.
QUEUE: list[str] = []

COMMON_ALIASES = {
    "damien": "damian",
    "damien's": "damian's",
    "harborcrest": "harbor crest",
    "harbour": "harbor",
    "ninety": "90",
    "leave": "lead",
}


def _env() -> dict:
    return {**os.environ, "PYTHONPATH": "src"}


def edit_row(ep: str) -> tuple[str, str]:
    text = PLAN.read_text(encoding="utf-8")
    m = re.search(rf"^\| {ep} \|.*?\|$", text, re.M)
    if not m:
        raise SystemExit(f"edit_plan row missing for {ep}")
    old = m.group(0)
    parts = [p.strip() for p in old.strip("|").split("|")]
    if len(parts) < 4:
        raise SystemExit(f"bad row {old}")
    parts[3] = f"硬剪含坏条并归档飞牛 `整集剪辑/{ep}`（未等重做）"
    if "FAIL" in parts[2] and "硬剪" not in parts[2]:
        parts[2] = parts[2] + "；硬剪保留坏条原片"
    new = "| " + " | ".join(parts) + " |"
    return old, new


def probe_frames(edit: Path, ep: str) -> dict[str, int]:
    out = {}
    for ud in sorted(
        (edit / "inputs").glob(f"{ep}-U*"),
        key=lambda p: int(p.name.split("-U")[1]),
    ):
        u = "U" + ud.name.split("-U")[1]
        mp4 = next(ud.glob("*.mp4"))
        raw = subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
                "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(mp4),
            ],
            text=True,
        ).strip()
        out[u] = int(raw.split(",")[0])
    return out


def stage(ep: str) -> Path:
    t0 = time.time()
    print(f"STAGE_BEGIN {ep}", flush=True)
    subprocess.check_call(
        [str(VENV_PY), "-u", str(STAGE_PY), ep],
        cwd=str(ROOT),
        env=_env(),
    )
    print(f"STAGE_DONE {ep} {time.time() - t0:.1f}s", flush=True)
    return ROOT / f".cache/lihun_{ep.lower()}_edit"


def render_only(ep: str, clips: dict, aliases: dict) -> tuple[str, str]:
    old, new = edit_row(ep)
    notes = [f"{u} hard-cut keep" for u in clips]
    t0 = time.time()
    print(f"RENDER_BEGIN {ep}", flush=True)
    cmd = [
        str(VENV_PY), "-u", str(RENDER_PY), ep,
        "--clips", json.dumps(clips),
        "--aliases", json.dumps(aliases),
        "--intent",
        f"Hard-cut {ep}: keep archive FAIL units as-is; sparse Undertow open only.",
        "--notes", json.dumps(notes),
        "--tail-pad", "24",
        "--hard-cut",
        "--skip-archive",
        "--edit-old", old,
        "--edit-new", new,
    ]
    subprocess.check_call(cmd, cwd=str(ROOT), env=_env())
    print(f"RENDER_DONE {ep} {time.time() - t0:.1f}s", flush=True)
    return old, new


def archive_only(ep: str, old: str, new: str) -> None:
    t0 = time.time()
    print(f"ARCHIVE_BEGIN {ep}", flush=True)
    subprocess.check_call(
        [
            str(VENV_PY), "-u", str(RENDER_PY), ep,
            "--archive-only",
            "--edit-old", old,
            "--edit-new", new,
        ],
        cwd=str(ROOT),
        env=_env(),
    )
    print(f"ARCHIVE_DONE {ep} {time.time() - t0:.1f}s", flush=True)


def _drain_done(pending: deque[tuple[str, Future]]) -> None:
    while pending and pending[0][1].done():
        ep, fut = pending.popleft()
        fut.result()
        print(f"ARCH_SLOT_FREE {ep}", flush=True)


def _await_slot(pending: deque[tuple[str, Future]], limit: int) -> None:
    """Block only when `limit` archives are already in flight."""
    _drain_done(pending)
    while len(pending) >= limit:
        ep, fut = pending[0]
        print(f"WAIT arch_slot ep={ep} in_flight={len(pending)}", flush=True)
        fut.result()
        pending.popleft()
        print(f"ARCH_SLOT_FREE {ep}", flush=True)
        _drain_done(pending)


def main() -> int:
    only = sys.argv[1:]
    eps = only if only else QUEUE
    if not eps:
        print("empty queue — pass EPxx args", flush=True)
        return 0

    subprocess.check_call(
        [
            str(VENV_PY), "-c",
            "from reexport_lihun_edits_v2 import warm_zh_map; warm_zh_map()",
        ],
        cwd=str(HERE),
        env=_env(),
    )

    print(f"PIPED_QUEUE {eps}", flush=True)
    print(
        f"PIPE v3 archive∥render; max {MAX_ARCH_IN_FLIGHT} archives in flight "
        "(no idle archive_before_put after next render)",
        flush=True,
    )
    t_batch = time.time()
    prep_edit = stage(eps[0])
    pending: deque[tuple[str, Future]] = deque()

    with ThreadPoolExecutor(max_workers=MAX_ARCH_IN_FLIGHT) as pool:
        for i, ep in enumerate(eps):
            print(f"\n======== HARD_CUT {ep} ========", flush=True)
            t_ep = time.time()
            frames = probe_frames(prep_edit, ep)
            clips = {u: [0, n] for u, n in frames.items()}
            print("clips", clips, flush=True)

            old, new = render_only(ep, clips, dict(COMMON_ALIASES))

            _await_slot(pending, MAX_ARCH_IN_FLIGHT)
            fut = pool.submit(archive_only, ep, old, new)
            pending.append((ep, fut))
            print(f"ARCH_SUBMIT {ep} in_flight={len(pending)}", flush=True)

            next_ep = eps[i + 1] if i + 1 < len(eps) else None
            if next_ep:
                prep_edit = stage(next_ep)

            print(
                f"RENDER_HANDOFF {ep} wall_so_far={time.time() - t_ep:.1f}s "
                f"(archives in flight={len(pending)})",
                flush=True,
            )

        print("WAIT archive_drain", flush=True)
        while pending:
            ep, fut = pending.popleft()
            fut.result()
            print(f"ARCH_SLOT_FREE {ep}", flush=True)

    print(f"BATCH_DONE n={len(eps)} wall={time.time() - t_batch:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
