"""Dry-run and receipt gates for Colab G4 FaceRefine host."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
import colab_h3_facerefine_g4_host as host  # noqa: E402


def test_facerefine_dry_run_cannot_allocate_paid_gpu(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sys, "argv", ["facerefine-host"])
    monkeypatch.setattr(
        host, "local_preflight",
        lambda **_kwargs: (tmp_path / "wheel.whl", "sha", True),
    )
    monkeypatch.setattr(
        host, "snapshot",
        lambda *args, **kwargs: pytest.fail("dry run must not query or allocate a paid session"),
    )
    host.main()
    out = capsys.readouterr().out
    assert '"paid_started": false' in out
    assert '"ready": true' in out


def test_facerefine_receipt_requires_verified_archive(tmp_path, monkeypatch):
    receipt = {
        "state": "success",
        "archive_state": "verified",
        "session_id": "session",
        "label": "FACEREFINE_EP01_U02",
        "prompt_id": "abc",
    }
    log = tmp_path / "facerefine.log"
    log.write_text("FACEREFINE_PHASE_RESULT " + json.dumps(receipt) + "\n")
    monkeypatch.setattr(host, "remote_json", lambda _: receipt)
    assert host.verify_phase("remote", "session", log) == receipt
    # local_staged is OK when Drive is over quota
    local = dict(receipt, archive_state="local_staged")
    log.write_text("FACEREFINE_PHASE_RESULT " + json.dumps(local) + "\n")
    assert host.verify_phase("remote", "session", log, local_meta=None)["archive_state"] == "local_staged"
    bad = dict(receipt, archive_state="pending")
    log.write_text("FACEREFINE_PHASE_RESULT " + json.dumps(bad) + "\n")
    with pytest.raises(RuntimeError, match="success criteria"):
        host.verify_phase("remote", "session", log)


def test_convert_ui_drops_muted_nodes():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
    import facerefine_ui_to_api as conv

    ui_path = Path(__file__).resolve().parents[1] / (
        "templates/yz_h3_facerefine_test/workflow_ui.auto_select.source.json"
    )
    ui = json.loads(ui_path.read_text(encoding="utf-8"))
    api = conv.convert_ui_workflow(ui)
    types = {n["class_type"] for n in api.values()}
    assert "H3FaceTrackCrop" in types
    assert "H3FaceStitch" in types
    assert "UnetLoaderGGUF" not in types  # muted
    assert "H3FaceMaskSAM" not in types  # muted
    # stitch should not require masks from muted SAM
    stitch = next(n for n in api.values() if n["class_type"] == "H3FaceStitch")
    assert "masks" not in stitch["inputs"]
