import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))
import colab_h3_test2_ep01_host as module
from colab_h3_a100_ab_host import ColabTransportLost


PREEXEC_LOST = (
    "runtime.execute_code(\n"
    "os.chdir('/content')\n"
    "RuntimeError: Connection was lost.\n"
)


def test_preexecution_transport_loss_reconnects_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = tmp_path / "setup.log"
    calls = []

    def fake_exec(session: str, path: Path, timeout: int, output: Path,
                  **environ: str) -> None:
        calls.append((session, path, timeout, output, environ))
        if len(calls) == 1:
            output.write_text(PREEXEC_LOST)
            raise ColabTransportLost("lost before script")
        output.write_text("comfy_ready")

    monkeypatch.setattr(module, "exec_file", fake_exec)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    module.exec_stage("session", Path("setup.py"), 900, log, KEY="value")
    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert (tmp_path / "setup-preexec-lost.log").read_text() == PREEXEC_LOST
    assert log.read_text() == "comfy_ready"


def test_transport_loss_after_script_start_is_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = tmp_path / "setup.log"
    calls = []

    def fake_exec(*_: object, **__: object) -> None:
        calls.append(1)
        log.write_text(PREEXEC_LOST + "RUN uv pip install\n")
        raise ColabTransportLost("lost after script started")

    monkeypatch.setattr(module, "exec_file", fake_exec)
    with pytest.raises(ColabTransportLost):
        module.exec_stage("session", Path("setup.py"), 900, log)
    assert len(calls) == 1
