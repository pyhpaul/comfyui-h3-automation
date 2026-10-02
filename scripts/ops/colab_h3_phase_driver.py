"""Run a measured H3 phase through the authenticated Colab CLI kernel."""

import os
import subprocess
import sys


TELEMETRY = "/content/colab_h3_telemetry.py"
METRICS = "/content/h3-u02-metrics"
PHASES = {
    "snapshot_base": ["snapshot", "--label", "base", "--python", "/usr/bin/python3.13"],
    "restore": ["run", "restore", "--", "python3", "/content/colab_h3_restore_entry.py"],
    "setup": ["run", "setup", "--", "python3", "/content/colab_h3_setup.py"],
    "snapshot_ready": ["snapshot", "--label", "ready", "--python",
                       "/content/h3-rental/ComfyUI/.venv/bin/python"],
    "check_nodes": ["check-nodes"],
    "u02": ["run", "u02", "--", "python3", "/content/colab_h3_run_u02.py"],
    "capture": ["capture"],
}


def main() -> None:
    phase = os.environ.get("H3_PHASE", "")
    if phase not in PHASES:
        raise ValueError(f"H3_PHASE must be one of {sorted(PHASES)}")
    command = [sys.executable, TELEMETRY, "--metrics-dir", METRICS, *PHASES[phase]]
    print(f"H3_PHASE={phase}", flush=True)
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
