import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for path in ("src", "scripts", "scripts/ops"):
    sys.path.insert(0, str(ROOT / path))
import h3_test2_ep01_child as child


def test_u02_accepts_hash_bound_recovered_u01_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous = tmp_path / "U01"
    (previous / "run").mkdir(parents=True)
    latent = "h3_context/ep01_u01_00001.safetensors"
    (previous / "phase.json").write_text(json.dumps({
        "state": "recovered", "archive_state": "verified",
    }))
    (previous / "run/validation.json").write_text(json.dumps({
        "latent_output_relative": latent, "latent": {"sha256": "frozen"},
    }))
    monkeypatch.setattr(child, "OUTPUT_ROOT", tmp_path)
    child.verify_local_parent("U02", latent)
    with pytest.raises(RuntimeError, match="verified U01"):
        child.verify_local_parent("U02", "h3_context/other.safetensors")
