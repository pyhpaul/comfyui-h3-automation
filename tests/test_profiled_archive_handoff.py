import importlib.util
import threading
from pathlib import Path


def _load():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_ep_units_profiled.py"
    spec = importlib.util.spec_from_file_location("run_ep_units_profiled", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_next_unit_queues_before_archive_finishes():
    module = _load()
    started = threading.Event()
    release = threading.Event()
    order: list[str] = []

    def archive() -> None:
        started.set()
        release.wait(5)
        order.append("archive")

    caller = threading.Thread(
        target=lambda: order.append(
            module.handoff_latent_then_archive(
                "h3_context/ep01_u03_00003.safetensors",
                archive,
            )[0]
        )
    )
    caller.start()
    assert started.wait(2)
    caller.join(1)
    assert caller.is_alive() is False
    assert order == ["h3_context/ep01_u03_00003.safetensors"]
    release.set()
