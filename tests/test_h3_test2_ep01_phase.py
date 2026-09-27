import os
import subprocess
import sys
from pathlib import Path


def test_phase_import_does_not_require_legacy_g4_run_environment() -> None:
    root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment.pop("H3_G4_REMOTE", None)
    environment["PYTHONPATH"] = os.pathsep.join(
        str(root / path) for path in ("src", "scripts", "scripts/ops")
    )
    completed = subprocess.run(
        [sys.executable, "-c", "import h3_test2_ep01_phase, h3_test2_ep01_child"],
        capture_output=True, text=True, env=environment, timeout=15,
    )
    assert completed.returncode == 0, completed.stderr
