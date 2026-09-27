"""Offline checks for the reversible one-step ComfyUI profiler patch."""

import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
import h3_a100_profile_hook as hook
from h3_a100_profile_runtime import _device_time_us


def archived_sampler_excerpt():
    return ("import math\n"
            "class Sampler:\n"
            "    def execute(self, noise, guider, sampler, sigmas, latent_image, "
            "noise_mask, callback, disable_pbar):\n"
            + hook.ANCHOR + "\n"
            "        return samples\n")


def test_profiler_hook_instruments_only_the_sampler_call():
    patched = hook.instrument_text(archived_sampler_excerpt())
    assert patched.count("profile_sampler(") == 1
    assert patched.count("guider.sample(") == 2
    assert "import os\n" in patched
    compile(patched, "nodes_custom_sampler.py", "exec")


def test_profiler_hook_requires_exact_anchor():
    with pytest.raises(RuntimeError, match="anchor mismatch"):
        hook.instrument_text("import math\n")


def test_profiler_hook_round_trip_without_touching_other_files(tmp_path, monkeypatch):
    root = tmp_path / "ComfyUI"
    source = root / hook.RELATIVE_SOURCE
    source.parent.mkdir(parents=True)
    original = archived_sampler_excerpt().encode()
    source.write_bytes(original)
    monkeypatch.setattr(hook, "EXPECTED_SHA256", hook.digest(original))
    backup_dir = tmp_path / "original"
    manifest = hook.install(root, backup_dir)
    assert manifest["original_sha256"] == hook.digest(original)
    assert source.read_bytes() != original
    hook.restore(root, backup_dir)
    assert source.read_bytes() == original
    assert (backup_dir / "nodes_custom_sampler.py").read_bytes() == original


def test_profiler_device_time_prefers_current_field():
    item = type("Event", (), {"self_device_time_total": 1250.0,
                              "self_cuda_time_total": 1.0})()
    assert _device_time_us(item) == 1250.0
