import os
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


def test_phase_import_does_not_require_legacy_g4_run_environment() -> None:
    root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment.pop("H3_G4_REMOTE", None)
    environment["PYTHONPATH"] = os.pathsep.join(
        str(root / path) for path in ("src", "scripts", "scripts/ops")
    )
    completed = subprocess.run(
        [sys.executable, "-c",
         "import h3_test2_ep01_phase, h3_test2_ep01_child, h3_test2_ep01_recovery"],
        capture_output=True, text=True, env=environment, timeout=15,
    )
    assert completed.returncode == 0, completed.stderr


def test_u02_phase_checks_recovered_parent_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    scripts = Path(__file__).resolve().parents[1] / "scripts/ops"
    sys.path.insert(0, str(scripts))
    import h3_test2_ep01_phase as phase

    root = tmp_path / "ComfyUI"
    latent = root / "output/h3_context/ep01_u01_00001.safetensors"
    latent.parent.mkdir(parents=True)
    latent.write_bytes(b"verified parent")
    previous = tmp_path / "h3-test2-ep01/U01/run"
    previous.mkdir(parents=True)
    relative = "h3_context/ep01_u01_00001.safetensors"
    (previous / "validation.json").write_text(json.dumps({
        "latent_output_relative": relative,
        "latent": {"sha256": hashlib.sha256(latent.read_bytes()).hexdigest()},
    }))
    monkeypatch.setattr(phase, "COMFY", root)
    monkeypatch.setattr(phase, "OUTPUT_ROOT", tmp_path / "h3-test2-ep01")
    phase.check_parent("U02", relative)
    latent.write_bytes(b"changed parent")
    with pytest.raises(RuntimeError, match="parent latent changed"):
        phase.check_parent("U02", relative)
