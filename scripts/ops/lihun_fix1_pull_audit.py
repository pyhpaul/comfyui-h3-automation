#!/usr/bin/env python3
"""Pull ready lihun fix1 candidates from Feiniu and run audit_candidate.

Does not issue registry verdicts — screening only. Use after Colab/GPU
have landed C1–C3 for a FAIL unit; safe to run while other units still render.

Layouts supported under 离婚后修复定版（10.22）/文戏工作流:
  - Colab: EPxx/Uyy/*.mp4 named EPxx-UyyC{n}-...
  - GPU:   EPxx/EPxx-UyyCn/*.mp4
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from comfy_orch.feiniu_archive import (  # noqa: E402
    PASSFILE, SHARE, connect_feiniu,
)

BATCH = r"离婚后修复定版（10.22）\文戏工作流"
REMOTE_ROOT = rf"H3_comfyUI_5090\archive\{BATCH}"
REVIEW = ROOT / ".cache" / "lihun_v23_fix1_review"
PROMPT_DIR = ROOT / ".cache" / "lihun_v23_fix1" / "input" / "prompts"
REGISTRY = ROOT / "runs" / "lihun_v23_fix_registry.json"
TAG_RE = re.compile(r"^(EP\d+-U\d+)(C\d+)-", re.I)


def fail_units() -> list[str]:
    text = (ROOT / "runs" / "lihun_v23_fix_plan.md").read_text(encoding="utf-8")
    return re.findall(r"^## FAIL-\d+ (EP\d+-U\d+)", text, re.M)


def list_remote_candidates(smb, unit: str) -> dict[str, tuple[str, str]]:
    """Return {C1: (remote_dir, filename), ...} for mp4s of this unit."""
    ep, u = unit.split("-", 1)
    found: dict[str, tuple[str, str]] = {}
    # GPU layout: EPxx/EPxx-UyyCn/
    try:
        items = smb.listPath(SHARE, rf"{REMOTE_ROOT}\{ep}\*")
    except Exception:
        return found
    for it in items:
        name = it.get_longname()
        if name in {".", ".."}:
            continue
        m_dir = re.match(rf"^{re.escape(unit)}(C\d+)$", name, re.I)
        if it.is_directory() and m_dir:
            tag = m_dir.group(1).upper()
            sub = rf"{REMOTE_ROOT}\{ep}\{name}"
            for f in smb.listPath(SHARE, sub + r"\*"):
                fn = f.get_longname()
                if fn.lower().endswith(".mp4"):
                    found[tag] = (sub, fn)
                    break
        elif not it.is_directory() and name.lower().endswith(".mp4"):
            m = TAG_RE.match(name)
            if m and m.group(1).upper() == unit.upper():
                found[m.group(2).upper()] = (rf"{REMOTE_ROOT}\{ep}\{u}", name)
    # Colab layout often puts all C*.mp4 under EPxx/Uyy/
    u_dir = rf"{REMOTE_ROOT}\{ep}\{u}"
    try:
        for f in smb.listPath(SHARE, u_dir + r"\*"):
            fn = f.get_longname()
            if f.is_directory() or not fn.lower().endswith(".mp4"):
                continue
            m = TAG_RE.match(fn)
            if m and m.group(1).upper() == unit.upper():
                found[m.group(2).upper()] = (u_dir, fn)
    except Exception:
        pass
    return found


def download_file(smb, remote_dir: str, name: str, dest: Path) -> object:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return smb
    buf = io.BytesIO()
    try:
        smb.getFile(SHARE, remote_dir + "\\" + name, buf.write)
    except Exception:
        try:
            smb.close()
        except Exception:
            pass
        smb = connect_feiniu(PASSFILE)
        buf = io.BytesIO()
        smb.getFile(SHARE, remote_dir + "\\" + name, buf.write)
    dest.write_bytes(buf.getvalue())
    return smb


def run_audit(unit: str, cand_dir: Path, prompt: Path) -> int:
    cmd = [
        str(ROOT / ".worktrees/feat-orch/.venv/bin/python"),
        str(ROOT / "scripts/ops/audit_candidate.py"),
        unit, str(cand_dir),
        "--prompt-source", str(prompt),
    ]
    env = {"PYTHONPATH": str(ROOT / "src"), **dict(**{k: v for k, v in __import__("os").environ.items()})}
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def registry_init(units: list[str]) -> None:
    cmd = [
        str(ROOT / ".worktrees/feat-orch/.venv/bin/python"),
        str(ROOT / "scripts/ops/fix_registry.py"),
        "--registry", str(REGISTRY),
        "init", "--units", *units, "--chains", "wenxi",
    ]
    subprocess.check_call(cmd, cwd=str(ROOT))


def registry_add(unit: str, tag: str, mp4: Path) -> None:
    data = json.loads(REGISTRY.read_text(encoding="utf-8")) if REGISTRY.exists() else {
        "slots": {}, "candidates": []}
    key = (unit, "wenxi", tag)
    for c in data.get("candidates", []):
        if (c["unit"], c["chain"], c["tag"]) == key:
            c["mp4"] = str(mp4)
            REGISTRY.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
            return
    subprocess.check_call([
        str(ROOT / ".worktrees/feat-orch/.venv/bin/python"),
        str(ROOT / "scripts/ops/fix_registry.py"),
        "--registry", str(REGISTRY),
        "add", "--unit", unit, "--chain", "wenxi", "--tag", tag,
        "--mp4", str(mp4),
    ], cwd=str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--units", nargs="*", default=None,
                    help="subset of FAIL units; default = all with ≥3 remote C*")
    ap.add_argument("--min-candidates", type=int, default=3)
    ap.add_argument("--audit", action="store_true",
                    help="run audit_candidate after pull")
    ap.add_argument("--audit-only", action="store_true",
                    help="skip Feiniu pull; audit pending dirs under review cache")
    ap.add_argument("--jobs", type=int, default=max(2, min(6, (os.cpu_count() or 4) // 2)),
                    help="parallel audit workers (default ~half CPUs, capped at 6)")
    ap.add_argument("--init-registry", action="store_true")
    ap.add_argument("--limit", type=int, default=0,
                    help="max units to process this invocation (0=all ready)")
    args = ap.parse_args()

    all_fails = fail_units()
    if args.init_registry:
        registry_init(all_fails)

    ready: list[tuple[str, dict[str, tuple[str, str]]]] = []
    pulled: list[tuple[str, str, Path, Path]] = []

    if args.audit_only:
        for unit_dir in sorted(REVIEW.iterdir() if REVIEW.is_dir() else []):
            if not unit_dir.is_dir():
                continue
            prompt = PROMPT_DIR / f"{unit_dir.name}.txt"
            if not prompt.is_file():
                continue
            for tag_dir in sorted(unit_dir.iterdir()):
                if not tag_dir.is_dir():
                    continue
                if not any(tag_dir.glob("*.mp4")):
                    continue
                pulled.append((unit_dir.name, tag_dir.name, tag_dir, prompt))
        print(f"AUDIT_ONLY pending_scan={len(pulled)} jobs={args.jobs}",
              flush=True)
    else:
        smb = connect_feiniu(PASSFILE)
        try:
            targets = args.units or all_fails
            for unit in targets:
                cands = list_remote_candidates(smb, unit)
                if len(cands) >= args.min_candidates:
                    ready.append((unit, cands))
            print(f"READY_UNITS {len(ready)}/{len(targets)} "
                  f"(need ≥{args.min_candidates} mp4)", flush=True)
            if args.limit:
                ready = ready[: args.limit]
            for unit, cands in ready:
                prompt = PROMPT_DIR / f"{unit}.txt"
                if not prompt.is_file():
                    print(f"SKIP {unit}: missing prompt {prompt}", flush=True)
                    continue
                for tag in sorted(cands):
                    remote_dir, fn = cands[tag]
                    cand_dir = REVIEW / unit / tag
                    dest = cand_dir / fn
                    print(f"PULL {unit}/{tag} <- {remote_dir}\\{fn}", flush=True)
                    smb = download_file(smb, remote_dir, fn, dest)
                    try:
                        smb = download_file(
                            smb, remote_dir, "prompt_h3.txt",
                            cand_dir / "prompt_h3.txt")
                    except Exception as exc:
                        print(f"WARN prompt_h3 {unit}/{tag}: {exc}", flush=True)
                    registry_add(unit, tag, dest)
                    pulled.append((unit, tag, cand_dir, prompt))
        finally:
            try:
                smb.close()
            except Exception:
                pass

    if args.audit or args.audit_only:
        pending = [
            (unit, tag, cand_dir, prompt)
            for unit, tag, cand_dir, prompt in pulled
            if not (cand_dir / "candidate_audit.json").is_file()
        ]
        skipped = len(pulled) - len(pending)
        print(f"AUDIT_QUEUE n={len(pending)} skip={skipped} jobs={args.jobs}",
              flush=True)

        def _one(item: tuple[str, str, Path, Path]) -> tuple[str, str, int]:
            unit, tag, cand_dir, prompt = item
            # Skip if another worker finished first.
            if (cand_dir / "candidate_audit.json").is_file():
                return unit, tag, 0
            print(f"AUDIT_START {unit}/{tag}", flush=True)
            rc = run_audit(unit, cand_dir, prompt)
            print(f"AUDIT_DONE {unit}/{tag} rc={rc}", flush=True)
            return unit, tag, rc

        fails = 0
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            futs = [pool.submit(_one, item) for item in pending]
            for fut in as_completed(futs):
                _unit, _tag, rc = fut.result()
                if rc:
                    fails += 1
        print(f"AUDIT_BATCH_DONE fail={fails}/{len(pending)}", flush=True)
    print(f"DONE processed={len(ready) or len(pulled)} out={REVIEW}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
