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
    report = json.loads(capsys.readouterr().out)
    assert report["paid_started"] is False
    assert report["restore_workers"] == 4


def test_g4_controls_use_small_pinned_bootstrap_and_restore_modules():
    destinations = {destination for _, destination in host.UPLOADS}
    assert "/content/rclone.gz" not in destinations
    assert {"/content/rclone-bootstrap.json", "/content/colab_h3_restore.py",
            "/content/colab_h3_restore_fast.py", "/content/colab_h3_restore_entry.py"} <= destinations
    for name in ("colab_h3_restore.py", "colab_h3_restore_fast.py", "colab_h3_restore_entry.py"):
        assert (host.SCRIPTS / name, f"/content/{name}") in host.UPLOADS


@pytest.mark.parametrize("workers", [1, 4])
def test_g4_restore_stages_bootstrap_first_and_pass_explicit_mode(workers):
    stages = host.setup_stages("wheel-sha", "remote", workers)
    names = [name for name, _, _, _ in stages]
    assert names.index("identity") < names.index("bootstrap") < names.index("restore")
    restore = next(stage for stage in stages if stage[0] == "restore")
    assert restore[1] == host.SCRIPTS / "colab_h3_restore_entry.py"
    assert restore[3] == {"H3_RESTORE_WORKERS": str(workers)}
    assert host.STAGE_MARKERS["bootstrap"] == "RCLONE_BOOTSTRAP_OK"


def test_g4_serial_override_is_reported_without_paid_allocation(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sys, "argv", ["g4-host", "--restore-workers", "1"])
    monkeypatch.setattr(host, "local_preflight", lambda: (tmp_path / "wheel.whl", "sha"))
    monkeypatch.setattr(host, "snapshot", lambda *args, **kwargs: pytest.fail("must not allocate"))
    host.main()
    report = json.loads(capsys.readouterr().out)
    assert report["restore_workers"] == 1
    assert report["paid_started"] is False


def test_g4_rejects_unmeasured_worker_count_before_preflight(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["g4-host", "--restore-workers", "8"])
    monkeypatch.setattr(host, "local_preflight", lambda: pytest.fail("must not preflight"))
    with pytest.raises(SystemExit):
        host.main()


@pytest.mark.parametrize("failed_stage", ["bootstrap", "restore"])
def test_failed_restore_admission_stops_without_generation(
        tmp_path, monkeypatch, failed_stage):
    monkeypatch.setattr(sys, "argv", ["g4-host", "--execute-paid"])
    monkeypatch.setattr(host, "BACKUP", tmp_path)
    reference = tmp_path / "reference.json"
    reference.write_text("{}")
    monkeypatch.setattr(host, "REFERENCE", reference)
    monkeypatch.setattr(host, "local_preflight", lambda: (tmp_path / "wheel.whl", "sha"))
    monkeypatch.setattr(host, "snapshot", lambda path, label: {
        "active": 0 if label == "before_assignment" else 1,
        "rate": 0 if label == "before_assignment" else 8.9, "balance": 80})
    # Every external dispatch is stubbed; --execute-paid exercises control flow only.
    monkeypatch.setattr(host, "run", lambda *args, **kwargs: "No active sessions found on server.")
    monkeypatch.setattr(host.subprocess, "Popen", lambda *args, **kwargs:
                        type("Watcher", (), {"poll": lambda self: None})())
    monkeypatch.setattr(host.time, "sleep", lambda _: None)
    stopped = []
    monkeypatch.setattr(host, "stop_and_verify", lambda *args: stopped.append(args))
    executed = []

    def execute(session, path, timeout, log, **env):
        name = log.stem
        executed.append((name, env))
        log.write_text("RuntimeError: SHA-256 mismatch" if name == failed_stage else
                       host.STAGE_MARKERS[name])

    monkeypatch.setattr(host, "exec_file", execute)
    monkeypatch.setattr(host, "verify_preflight", lambda *args: pytest.fail("must not proceed"))
    with pytest.raises(RuntimeError, match=f"{failed_stage} stage had no success marker"):
        host.main()
    assert executed[-1][0] == failed_stage
    assert not any(name in {"setup", "preflight", "G4_U02"} for name, _ in executed)
    assert len(stopped) == 1
    if failed_stage == "restore":
        assert executed[-1][1] == {"H3_RESTORE_WORKERS": "4"}
