"""Offline admission and receipt gates for the single G4 U02 trial."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
import colab_h3_g4_u02_host as host


def preflight_report() -> dict:
    assets = [{"path": f"/content/asset-{index}", "match": True} for index in range(12)]
    assets.append({"path": "/content/h3-runner/src/comfy_orch/gpu_adapt.py",
                   "sha256": host.RESTORED_GPU_ADAPT_SHA256, "match": True})
    return {"assets": assets, "parent_match": True}


def test_g4_preflight_rejects_any_mismatch(monkeypatch):
    report = preflight_report()
    monkeypatch.setattr(host, "remote_json", lambda _: report)
    host.verify_preflight("remote")
    report["assets"][0]["match"] = False
    with pytest.raises(RuntimeError, match="did not pass"):
        host.verify_preflight("remote")
    report["assets"][0]["match"] = True
    report["assets"][-1]["sha256"] = "wrong"
    with pytest.raises(RuntimeError, match="did not pass"):
        host.verify_preflight("remote")


def test_g4_receipt_reconciles_after_short_transport_timeout(tmp_path, monkeypatch):
    manifest = b'{"assets": []}'
    local = {"session_id": "session", "label": "G4_U02", "state": "success",
             "input_manifest_sha256": hashlib.sha256(manifest).hexdigest()}
    receipt = {**local, "archive_state": "verified"}
    log = tmp_path / "G4_U02.log"
    log.write_text("G4_U02_PHASE_RESULT " + json.dumps(local) + "\n")
    monkeypatch.setattr(host, "remote_json", lambda _: receipt)
    monkeypatch.setattr(host.subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args[0], 0, stdout=manifest))
    assert host.verify_phase("remote", "session", log) == receipt
    receipt["archive_state"] = "missing"
    with pytest.raises(RuntimeError, match="do not match"):
        host.verify_phase("remote", "session", log)


def test_g4_dry_run_cannot_allocate_paid_gpu(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sys, "argv", ["g4-host"])
    monkeypatch.setattr(host, "local_preflight", lambda: (tmp_path / "wheel.whl", "sha"))
    monkeypatch.setattr(host, "snapshot", lambda *args, **kwargs:
                        pytest.fail("dry run must not query or allocate a paid session"))
    host.main()
    assert '"paid_started": false' in capsys.readouterr().out
