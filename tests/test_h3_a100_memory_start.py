"""Prove the rental default and A100 memory trial differ by one CLI flag."""

import os
import subprocess
from pathlib import Path


START = Path(__file__).resolve().parents[1] / "scripts/ops/comfy_gpu_start.sh"


def start_arguments(tmp_path, mode):
    root = tmp_path / mode
    (root / ".venv/bin").mkdir(parents=True)
    (root / ".venv/bin/activate").write_text("")
    fake_bin = root / "fake-bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python"
    fake_python.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n")
    fake_python.chmod(0o755)
    log = root / "comfy.log"
    env = os.environ.copy()
    env.update({"COMFY_ROOT": str(root), "COMFY_H3_LOG": str(log),
                "H3_DISABLE_SMART_MEMORY": mode,
                "PATH": str(fake_bin) + os.pathsep + env["PATH"]})
    subprocess.run(["bash", str(START)], env=env, check=True, timeout=5)
    return log.read_text().splitlines()


def test_memory_startup_changes_only_disable_smart_memory(tmp_path):
    baseline = start_arguments(tmp_path, "1")
    candidate = start_arguments(tmp_path, "0")
    assert baseline[0] == candidate[0] == "main.py"
    assert "--disable-smart-memory" in baseline
    assert "--disable-smart-memory" not in candidate
    assert [arg for arg in baseline if arg != "--disable-smart-memory"] == candidate
