"""Cold-directory and budget gates for the restore-only experiment."""

import json
import io
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
import colab_h3_restore_benchmark as bench
import colab_h3_restore_benchmark_host as host


def test_tee_preserves_active_notebook_stdout(monkeypatch):
    terminal = io.StringIO()
    log = io.StringIO()
    monkeypatch.setattr(sys, "stdout", terminal)
    tee = bench.Tee(log)
    tee.write("runtime progress\n")
    tee.flush()
    assert terminal.getvalue() == "runtime progress\n"
    assert log.getvalue() == terminal.getvalue()


def test_model_time_requires_exactly_one_marker():
    assert bench.model_seconds("model_restore_seconds 12.5\n") == 12.5
    for text in ("", "model_restore_seconds 1\nmodel_restore_seconds 2\n"):
        with pytest.raises(RuntimeError, match="model timing"):
            bench.model_seconds(text)


def test_report_requires_session_and_both_hash_verified_cold_runs():
    report = {"state": "success", "session_id": "test", "runs": [
        {"label": label, "cold": True, "verified_models": 6, "workers": workers,
         "restore_seconds": seconds, "model_seconds": seconds - 1,
         "models": json.loads(host.MANIFEST.read_text())["models"]}
        for label, workers, seconds in (("baseline", 1, 20), ("candidate", 4, 10))]}
    host.verify_report(report, "test")
    report["runs"][1]["cold"] = False
    with pytest.raises(RuntimeError, match="verified cold"):
        host.verify_report(report, "test")


def test_deadline_preserves_stop_margin():
    assert host.work_seconds(100, 100, rate=8.9, cap=5, max_minutes=30) == 1680
    assert host.work_seconds(100, 160, rate=20, cap=5, max_minutes=30) == 648
    with pytest.raises(RuntimeError, match="budget"):
        host.work_seconds(100, 1800, rate=8.9, cap=5, max_minutes=30)


def test_host_dry_run_never_queries_or_allocates_paid_session(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["restore-benchmark-host"])
    monkeypatch.setattr(host, "local_inputs", lambda: [])
    monkeypatch.setattr(host, "snapshot", lambda *a, **kw:
                        pytest.fail("dry run must not access paid sessions"))
    host.main()
    assert json.loads(capsys.readouterr().out)["paid_started"] is False
