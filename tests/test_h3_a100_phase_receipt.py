"""Offline identity, terminal publication and silent-CLI receipt tests."""

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
import colab_h3_a100_ab_host as host
import colab_h3_a100_profile_host as profile_host
from h3_a100_phase_receipt import (ReceiptIdentity, identity_from_environment,
                                    publish_verified, receipt_status)


def identity():
    return ReceiptIdentity("session-1", "P_C", "attempt-1", "a" * 64)


def test_receipt_requires_identity_time_and_verified_archive():
    attempted = datetime.now(timezone.utc)
    receipt = {**vars(identity()), "state": "success", "archive_state": "verified",
               "started_at_utc": attempted.isoformat()}
    assert receipt_status(receipt, identity(), attempted) == "success"
    receipt["attempt_id"] = "another-attempt"
    assert receipt_status(receipt, identity(), attempted) == "wrong_attempt_id"
    receipt["attempt_id"] = identity().attempt_id
    receipt["archive_state"] = "pending"
    assert receipt_status(receipt, identity(), attempted) == "unverified_archive"
    receipt["archive_state"] = "verified"
    receipt["started_at_utc"] = (attempted - timedelta(minutes=1)).isoformat()
    assert receipt_status(receipt, identity(), attempted) == "stale"


def test_manifest_hash_must_match_host_admission(tmp_path, monkeypatch):
    manifest = tmp_path / "preflight.json"
    manifest.write_text('{"ok":true}\n')
    monkeypatch.setenv("H3_INPUT_MANIFEST_SHA256", "wrong")
    with pytest.raises(RuntimeError, match="manifest changed"):
        identity_from_environment("P_C", manifest)


def test_terminal_receipt_is_published_after_payload_check(tmp_path, monkeypatch):
    output = tmp_path / "output"
    output.mkdir()
    (output / "trace.json").write_text("trace")
    phase = output / "phase.json"
    phase.write_text(json.dumps({"state": "success", **vars(identity())}))
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[3] == "cat":
            return subprocess.CompletedProcess(command, 0, stdout=phase.read_bytes())
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    publish_verified(output, "remote:P_C", Path("/rclone"), Path("/config"))
    assert [item[3] for item in calls] == ["copy", "check", "copyto", "cat"]
    assert "--exclude" in calls[0] and "phase.json" in calls[0]
    assert json.loads(phase.read_text())["archive_state"] == "verified"


def test_failed_payload_check_never_publishes_terminal_receipt(tmp_path, monkeypatch):
    output = tmp_path / "output"
    output.mkdir()
    phase = output / "phase.json"
    phase.write_text(json.dumps({"state": "failed", **vars(identity())}))
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command[3])
        if command[3] == "check":
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(subprocess.CalledProcessError):
        publish_verified(output, "remote:P_C", Path("/rclone"), Path("/config"))
    assert calls == ["copy", "check"]
    assert "archive_state" not in json.loads(phase.read_text())


def test_silent_cli_is_stopped_when_verified_receipt_arrives(tmp_path):
    command = [sys.executable, "-c", "import time; time.sleep(30)"]
    started = time.monotonic()
    with pytest.raises(host.PhaseReceiptTerminal) as caught:
        host.run(command, tmp_path / "silent.log", timeout=20,
                 poll_receipt=lambda: "failed", receipt_poll_interval=0.1)
    assert caught.value.state == "failed"
    assert time.monotonic() - started < 5


def test_unreachable_remote_receipt_does_not_claim_success(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 5)

    monkeypatch.setattr(host.subprocess, "run", timeout)
    assert host.verified_remote_state("remote:phase.json", identity(),
                                      datetime.now(timezone.utc)) is None


def test_phase_exec_binds_session_attempt_and_manifest(tmp_path, monkeypatch):
    calls = []

    def fake_run(command, *args, **kwargs):
        calls.append((command, kwargs))
        return ""

    monkeypatch.setattr(host, "run", fake_run)
    monkeypatch.setattr(host, "verified_remote_state", lambda *args: "success")
    host.exec_file("session-1", tmp_path / "phase.py", 30, tmp_path / "phase.log",
                   phase_label="P_C", receipt_path="remote:P_C/phase.json",
                   input_manifest_sha256="a" * 64, host_timeout=35)
    command, options = calls[0]
    assert options["timeout"] == 35
    assert "--env" in command
    assert "H3_SESSION_ID=session-1" in command
    assert "H3_INPUT_MANIFEST_SHA256=" + "a" * 64 in command
    assert any(item.startswith("H3_ATTEMPT_ID=") for item in command)


def test_profile_budget_and_paid_flag_are_fail_closed(tmp_path, monkeypatch):
    past = time.monotonic() - 1
    with pytest.raises(TimeoutError, match="stage deadline"):
        profile_host.bounded_timeout(past, datetime.now(timezone.utc), 10)
    monkeypatch.setattr(sys, "argv", ["profile", "--max-cu", "6"])
    monkeypatch.setattr(profile_host, "require_profile_files",
                        lambda: pytest.fail("must not inspect paid inputs"))
    with pytest.raises(ValueError, match="--execute-paid"):
        profile_host.main()
    monkeypatch.setattr(sys, "argv", ["profile", "--execute-paid", "--max-cu", "6"])
    with pytest.raises(ValueError, match="--attended"):
        profile_host.main()
    monkeypatch.setattr(sys, "argv", ["profile", "--execute-paid", "--attended",
                                       "--max-cu", "6"])
    with pytest.raises(RuntimeError, match="Gate 1 is disabled"):
        profile_host.main()


def test_stage_deadline_covers_manifest_and_usage(tmp_path, monkeypatch):
    past = time.monotonic() - 1
    monkeypatch.setattr(host.subprocess, "run", lambda *args, **kwargs:
                        pytest.fail("expired stage must not call a subprocess"))
    with pytest.raises(TimeoutError, match="stage deadline"):
        host.remote_manifest_sha256("remote:P_C/phase.json", past)
    with pytest.raises(TimeoutError, match="stage deadline"):
        host.snapshot(tmp_path / "cu.jsonl", "stage", past)
    with pytest.raises(TimeoutError, match="stage deadline"):
        host.exec_file("session", tmp_path / "phase.py", 1200, tmp_path / "phase.log",
                       phase_label="P_C", receipt_path="remote:P_C/phase.json",
                       stage_end=past)


def test_expired_reconcile_does_not_delay_stop(tmp_path, monkeypatch):
    monkeypatch.setattr(host.subprocess, "run", lambda *args, **kwargs:
                        pytest.fail("expired reconcile must not call a subprocess"))
    host.reconcile_phase("P_C", datetime.now(timezone.utc), tmp_path / "phase.log",
                         stage_end=time.monotonic() - 1)
    report = json.loads((tmp_path / "phase.reconcile.json").read_text())
    assert report["receipt_status"] == "unavailable"
    assert report["usage_error"] == "TimeoutError"


def test_stop_confirms_zero_usage_before_releasing_watchdog(tmp_path, monkeypatch):
    events = []

    class Watcher:
        def poll(self):
            return None

        def terminate(self):
            events.append("watchdog_terminated")

        def wait(self, timeout):
            return 0

    def fake_run(command, *args, **kwargs):
        events.append(command[1])
        return "No active sessions" if command[1] == "sessions" else ""

    monkeypatch.setattr(host, "run", fake_run)
    monkeypatch.setattr(host, "snapshot", lambda *args: {"active": 0, "rate": 0})
    host.stop_and_verify("session-1", tmp_path, Watcher())
    assert events == ["stop", "sessions", "watchdog_terminated"]


def test_profile_host_dry_run_stops_after_phase_failure(tmp_path, monkeypatch):
    events = []

    class Watcher:
        def poll(self):
            return None

    def snapshot(_path, label, _stage_end=None):
        if label == "before_assignment":
            return {"active": 0, "rate": 0, "balance": 100}
        return {"active": 1, "rate": 6.77, "balance": 99}

    def fail_phase(*args, **kwargs):
        raise RuntimeError("phase failed")

    monkeypatch.setattr(sys, "argv", ["profile", "--execute-paid", "--attended",
                                       "--max-cu", "6"])
    monkeypatch.setattr(profile_host, "BACKUP", tmp_path)
    monkeypatch.setattr(profile_host, "PROFILE_GATE1_ENABLED", True)
    monkeypatch.setattr(profile_host, "require_profile_files", lambda: None)
    monkeypatch.setattr(profile_host, "snapshot", snapshot)
    monkeypatch.setattr(profile_host, "run", lambda command, *args, **kwargs:
                        events.append(command[:2]))
    monkeypatch.setattr(profile_host, "upload_controls", lambda *args: None)
    monkeypatch.setattr(profile_host, "restore_and_preflight", lambda *args: None)
    monkeypatch.setattr(profile_host, "admit_next", lambda *args: None)
    monkeypatch.setattr(profile_host, "exec_file", fail_phase)
    monkeypatch.setattr(profile_host, "stop_and_verify", lambda *args:
                        events.append("stopped"))
    monkeypatch.setattr(profile_host.subprocess, "Popen", lambda *args, **kwargs: Watcher())
    monkeypatch.setattr(profile_host.time, "sleep", lambda seconds: None)
    with pytest.raises(RuntimeError, match="phase failed"):
        profile_host.main()
    assert events[0] == ["colab", "new"]
    assert "stopped" in events
