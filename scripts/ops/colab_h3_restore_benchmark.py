"""Restore-only A/B in separate empty directories on one disposable Colab VM."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
from contextlib import redirect_stdout
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

import colab_h3_restore as base
import colab_h3_restore_fast as fast


class Tee:
    def __init__(self, stream):
        self.stream = stream
        self.terminal = sys.stdout

    def write(self, text):
        self.terminal.write(text)
        return self.stream.write(text)

    def flush(self):
        self.stream.flush()
        self.terminal.flush()


def model_seconds(log: str) -> float:
    lines = [line for line in log.splitlines() if line.startswith("model_restore_seconds ")]
    if len(lines) != 1:
        raise RuntimeError("restore did not emit exactly one model timing")
    return float(lines[0].split()[1])


def configure_root(root: Path) -> None:
    root.mkdir(exist_ok=False)
    for name in ("rclone.gz", "rclone.conf"):
        shutil.copyfile(Path("/content") / name, root / name)
    os.chmod(root / "rclone.conf", 0o600)
    base.CONTENT = root
    base.COMFY_ROOT = root / "h3-rental/ComfyUI"
    base.RCLONE = root / "rclone"
    base.CONFIG = root / "rclone.conf"


def verify_models(manifest: dict) -> list[dict]:
    records = []
    for model in manifest["models"]:
        path = base.COMFY_ROOT / "models" / model["relative_path"]
        size = path.stat().st_size
        digest = base.sha256(path)
        if size != model["bytes"] or digest != model["sha256"]:
            raise RuntimeError(f"benchmark model verification failed: {model['relative_path']}")
        records.append({"relative_path": model["relative_path"], "bytes": size, "sha256": digest})
    return records


def run_restore(root: Path, label: str, workers: int, manifest: dict) -> dict:
    configure_root(root / label)
    log = root / f"{label}.log"
    callback = (base.restore_split_model if workers == 1 else
                partial(fast.restore_split_model, options=fast.RestoreOptions(workers)))
    started = time.monotonic()
    with log.open("w") as stream, redirect_stdout(Tee(stream)):
        base.main(restore_model=callback)
    elapsed = time.monotonic() - started
    log_text = log.read_text()
    if "model_cached_verified" in log_text or '"reused_parts": 1' in log_text:
        raise RuntimeError("benchmark unexpectedly reused a local model cache")
    metrics = [json.loads(line.split(" ", 1)[1]) for line in log_text.splitlines()
               if line.startswith("fast_model_metrics ")]
    if any(item["reused_parts"] for item in metrics):
        raise RuntimeError("benchmark unexpectedly reused part cache")
    started = time.monotonic()
    models = verify_models(manifest)
    return {"label": label, "workers": workers, "cold": True,
            "restore_seconds": elapsed, "model_seconds": model_seconds(log_text),
            "validation_seconds": time.monotonic() - started,
            "verified_models": len(models), "models": models, "model_metrics": metrics,
            "free_bytes_after": shutil.disk_usage(root).free}


def save_report(root: Path, report: dict) -> None:
    staging = root / "report.json.tmp"
    staging.write_text(json.dumps(report, indent=2) + "\n")
    staging.replace(root / "report.json")


def main() -> None:
    session = os.environ["H3_RESTORE_BENCH_SESSION"]
    if not session.startswith("h3-restore-") or not all(c.isalnum() or c == "-" for c in session):
        raise ValueError("invalid benchmark session name")
    manifest = json.loads(Path("/content/restore-manifest.json").read_text())
    root = Path("/content") / session
    root.mkdir(exist_ok=False)
    free = shutil.disk_usage(root).free
    if free < 110 * 1024 ** 3:
        raise RuntimeError(f"benchmark requires 110 GiB free; found {free / 1024 ** 3:.1f} GiB")
    smi = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                          "--format=csv,noheader"], capture_output=True, text=True,
                         check=True, timeout=15).stdout.strip()
    scripts = ("colab_h3_restore.py", "colab_h3_restore_fast.py", "colab_h3_restore_benchmark.py")
    report = {"state": "running", "session_id": session, "runs": [],
              "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "python": platform.python_version(), "gpu": smi, "free_bytes_before": free,
              "script_hashes": {name: base.sha256(Path("/content") / name) for name in scripts},
              "scope": "restore_only_no_dependency_install_or_inference",
              "order": ["baseline", "candidate"]}
    save_report(root, report)
    try:
        for label, workers in (("baseline", 1), ("candidate", 4)):
            print(f"RESTORE_BENCH_START {label} workers={workers}", flush=True)
            result = run_restore(root, label, workers, manifest)
            report["runs"].append(result)
            save_report(root, report)
            print("RESTORE_BENCH_RUN " + json.dumps(result), flush=True)
        baseline, candidate = report["runs"]
        delta = baseline["restore_seconds"] - candidate["restore_seconds"]
        report.update({"state": "success", "saved_seconds": delta,
                       "saved_percent": 100 * delta / baseline["restore_seconds"],
                       "speedup": baseline["restore_seconds"] / candidate["restore_seconds"]})
        save_report(root, report)
        print("RESTORE_BENCH_RESULT " + json.dumps(report), flush=True)
    except Exception as exc:
        report.update({"state": "failed", "error_type": type(exc).__name__, "error": str(exc)})
        save_report(root, report)
        print("RESTORE_BENCH_FAILED " + json.dumps(report), flush=True)
        raise


if __name__ == "__main__":
    main()
