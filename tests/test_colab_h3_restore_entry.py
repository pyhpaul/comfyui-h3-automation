"""Offline routing gates for the formal Colab restore entrypoint."""

import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
import colab_h3_restore as base
import colab_h3_restore_entry as entry
import colab_h3_restore_fast as fast
import colab_h3_phase_driver as phases


def test_default_entry_uses_four_workers(monkeypatch, capsys):
    monkeypatch.delenv("H3_RESTORE_WORKERS", raising=False)
    seen = []
    monkeypatch.setattr(base, "main", lambda **kwargs: seen.append(kwargs))
    entry.main()
    callback = seen[0]["restore_model"]
    assert callback.func is fast.restore_split_model
    assert callback.keywords["options"].workers == 4
    assert "RESTORE_MODE workers=4" in capsys.readouterr().out


def test_explicit_serial_entry_uses_original_transport(monkeypatch, capsys):
    monkeypatch.setenv("H3_RESTORE_WORKERS", "1")
    seen = []
    monkeypatch.setattr(base, "main", lambda **kwargs: seen.append(kwargs))
    entry.main()
    assert seen == [{"restore_model": base.restore_split_model}]
    assert "RESTORE_MODE workers=1" in capsys.readouterr().out


@pytest.mark.parametrize("workers", ["0", "2", "8", "bad", ""])
def test_invalid_mode_stops_before_restoration(monkeypatch, workers):
    monkeypatch.setenv("H3_RESTORE_WORKERS", workers)
    monkeypatch.setattr(base, "main", lambda **kwargs: pytest.fail("must not restore"))
    with pytest.raises(ValueError, match="H3_RESTORE_WORKERS"):
        entry.main()


def test_failure_does_not_automatically_retry_serial(monkeypatch):
    monkeypatch.setenv("H3_RESTORE_WORKERS", "4")
    seen = []

    def failed(**kwargs):
        seen.append(kwargs)
        raise RuntimeError("SHA-256 mismatch")

    monkeypatch.setattr(base, "main", failed)
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        entry.main()
    assert len(seen) == 1


def test_telemetry_restore_uses_formal_entry_and_inherits_mode(monkeypatch):
    monkeypatch.setenv("H3_PHASE", "restore")
    monkeypatch.setenv("H3_RESTORE_WORKERS", "1")
    commands = []
    monkeypatch.setattr(phases.subprocess, "run",
                        lambda command, **kwargs: commands.append((command, kwargs)))
    phases.main()
    command, kwargs = commands[0]
    assert command[-1] == "/content/colab_h3_restore_entry.py"
    assert kwargs == {"check": True}
