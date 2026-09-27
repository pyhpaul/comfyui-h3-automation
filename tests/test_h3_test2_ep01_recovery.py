import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))
import h3_test2_ep01_recovery as module
from h3_test2_ep01_recovery import validate_recovery_manifest


def recovery() -> dict:
    return json.loads((ROOT / "docs/ops/test2-ep01-u01-recovery-v1.json").read_text())


def manifest_sha() -> str:
    return hashlib.sha256((ROOT / "docs/ops/drive-test2-ep01-v1.json").read_bytes()).hexdigest()


def test_frozen_u01_recovery_matches_h3_grid_and_source_paths() -> None:
    validate_recovery_manifest(recovery(), manifest_sha())


@pytest.mark.parametrize("field", ["latent_remote", "video_remote", "source_phase_remote"])
def test_recovery_rejects_changed_source_path(field: str) -> None:
    changed = copy.deepcopy(recovery())
    changed[field] += "-decoy"
    with pytest.raises(RuntimeError, match="approved source"):
        validate_recovery_manifest(changed, manifest_sha())


def test_recovery_rejects_old_latent_shape_assumption() -> None:
    changed = copy.deepcopy(recovery())
    changed["validation"]["latent"]["tensors"][1]["shape"][2] = 122
    with pytest.raises(RuntimeError, match="latent shape"):
        validate_recovery_manifest(changed, manifest_sha())


def test_recovery_stage_installs_parent_without_resubmitting_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = recovery()
    fake_latent = tmp_path / "source.safetensors"
    fake_latent.write_bytes(b"frozen latent bytes")
    record["validation"]["latent"]["bytes"] = fake_latent.stat().st_size
    record["validation"]["latent"]["sha256"] = hashlib.sha256(fake_latent.read_bytes()).hexdigest()
    content = tmp_path / "content"
    content.mkdir()
    recovery_path = content / "test2-ep01-u01-recovery.json"
    recovery_path.write_text(json.dumps(record))
    input_manifest = content / "test2-ep01-input-manifest.json"
    shutil.copyfile(ROOT / "docs/ops/drive-test2-ep01-v1.json", input_manifest)
    monkeypatch.setattr(module, "CONTENT", content)
    monkeypatch.setattr(module, "RECOVERY", recovery_path)
    monkeypatch.setattr(module, "INPUT_MANIFEST", input_manifest)
    monkeypatch.setattr(module, "OUTPUT", content / "h3-test2-ep01/U01")
    monkeypatch.setattr(module, "LATENT_ROOT", content / "ComfyUI/output")
    monkeypatch.setattr(module, "RCLONE", content / "rclone")
    monkeypatch.setattr(module, "CONFIG", content / "rclone.conf")
    monkeypatch.setattr(module, "verify_recovery_sources", lambda *_: None)
    monkeypatch.setenv("H3_TEST2_REMOTE", "drive:next-session")
    commands = []

    def fake_run(command: list[str], **_: object) -> None:
        commands.append(command)
        if command[2] == record["latent_remote"]:
            shutil.copyfile(fake_latent, command[3])

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    module.main()
    phase = json.loads((module.OUTPUT / "phase.json").read_text())
    validation = json.loads((module.OUTPUT / "run/validation.json").read_text())
    report = json.loads((content / "test2-ep01-u01-recovery-report.json").read_text())
    assert phase["state"] == "recovered"
    assert validation["prompt_id"] == record["validation"]["prompt_id"]
    assert report["latent_sha256"] == record["validation"]["latent"]["sha256"]
    assert len(commands) == 2
    assert commands[1][3] == "drive:next-session/recovery-u01.json"
