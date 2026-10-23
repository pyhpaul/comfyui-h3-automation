"""Offline transport, cache and publication gates for the opt-in restore."""

import hashlib
import subprocess
import sys
import threading
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
import colab_h3_restore as base
import colab_h3_restore_fast as fast
import colab_h3_restore_entry as entry


@pytest.fixture
def transport(tmp_path, monkeypatch):
    monkeypatch.setattr(base, "CONTENT", tmp_path)
    monkeypatch.setattr(base, "PART_SIZE", 4)
    payload = b"abcdefghijklmnopqr"
    parts = [payload[index:index + 4] for index in range(0, len(payload), 4)]
    calls = []

    def download(command, **kwargs):
        index = int(command[2].rsplit("-", 1)[1])
        calls.append(index)
        Path(command[3]).write_bytes(parts[index])
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(fast.subprocess, "run", download)
    return payload, parts, calls


def restore(tmp_path, payload, workers=2):
    options = fast.RestoreOptions(workers=workers, part_timeout=10)
    fast.restore_split_model(tmp_path / "models", "x/model.safetensors", len(payload),
                             hashlib.sha256(payload).hexdigest(), options=options)


def test_parallel_completion_is_assembled_in_order(tmp_path, monkeypatch, transport):
    payload, parts, calls = transport
    second_finished = threading.Event()
    both_started = threading.Barrier(2)
    lock = threading.Lock()
    active = 0
    peak = 0

    def download(command, **kwargs):
        nonlocal active, peak
        index = int(command[2].rsplit("-", 1)[1])
        with lock:
            active += 1
            peak = max(peak, active)
        if index < 2:
            both_started.wait(timeout=5)
        if index == 0:
            assert second_finished.wait(5), "second part must overlap the first"
        Path(command[3]).write_bytes(parts[index])
        calls.append(index)
        if index == 1:
            second_finished.set()
        with lock:
            active -= 1
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(fast.subprocess, "run", download)
    restore(tmp_path, payload)
    assert peak == 2
    assert calls[0] == 1
    assert sorted(calls) == list(range(len(parts)))
    assert (tmp_path / "models/x/model.safetensors").read_bytes() == payload
    assert not list((tmp_path / "h3-part-cache").rglob("part-*"))


@pytest.mark.parametrize("workers", [0, -1, 9])
def test_invalid_concurrency_rejected(workers):
    with pytest.raises(ValueError, match="workers"):
        fast.RestoreOptions(workers=workers)


def test_failed_download_resumes_completed_parts(tmp_path, monkeypatch, transport):
    payload, parts, calls = transport
    output = tmp_path / "models/x/model.safetensors"

    def broken(command, **kwargs):
        index = int(command[2].rsplit("-", 1)[1])
        calls.append(index)
        if index == 2:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        Path(command[3]).write_bytes(parts[index])
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(fast.subprocess, "run", broken)
    with pytest.raises(subprocess.TimeoutExpired):
        restore(tmp_path, payload, workers=1)
    assert not output.exists()
    assert not output.with_name(output.name + ".incomplete").exists()
    assert len(list((tmp_path / "h3-part-cache").rglob("part-???"))) == 2
    calls.clear()

    def recovered(command, **kwargs):
        index = int(command[2].rsplit("-", 1)[1])
        calls.append(index)
        Path(command[3]).write_bytes(parts[index])
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(fast.subprocess, "run", recovered)
    restore(tmp_path, payload, workers=1)
    assert calls == [2, 3, 4]
    assert output.read_bytes() == payload


def test_wrong_size_never_publishes(tmp_path, monkeypatch, transport):
    payload, parts, calls = transport

    def truncated(command, **kwargs):
        Path(command[3]).write_bytes(b"bad")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(fast.subprocess, "run", truncated)
    with pytest.raises(RuntimeError, match="wrong part size"):
        restore(tmp_path, payload)
    assert not (tmp_path / "models/x/model.safetensors").exists()
    assert not list((tmp_path / "h3-part-cache").rglob("*.download"))


def test_bad_digest_preserves_existing_output_and_discards_bad_cache(
        tmp_path, monkeypatch, transport):
    payload, parts, calls = transport
    output = tmp_path / "models/x/model.safetensors"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"original")

    def corrupt(command, **kwargs):
        index = int(command[2].rsplit("-", 1)[1])
        Path(command[3]).write_bytes(b"z" * len(parts[index]))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(fast.subprocess, "run", corrupt)
    with pytest.raises(RuntimeError, match="reassembled model mismatch"):
        restore(tmp_path, payload)
    assert output.read_bytes() == b"original"
    assert not list((tmp_path / "h3-part-cache").rglob("part-*"))


def test_verified_existing_model_skips_network(tmp_path, transport):
    payload, parts, calls = transport
    output = tmp_path / "models/x/model.safetensors"
    output.parent.mkdir(parents=True)
    output.write_bytes(payload)
    restore(tmp_path, payload)
    assert calls == []


def test_short_cached_part_is_redownloaded(tmp_path, transport):
    payload, parts, calls = transport
    cache = tmp_path / "h3-part-cache" / hashlib.sha256(payload).hexdigest()
    cache.mkdir(parents=True)
    (cache / "part-000").write_bytes(b"x")
    restore(tmp_path, payload)
    assert 0 in calls


def test_candidate_passes_options_into_base_main(monkeypatch):
    seen = []
    monkeypatch.setattr(sys, "argv", ["restore-fast", "--workers", "3"])
    monkeypatch.setattr(base, "main", lambda **kwargs: seen.append(kwargs))
    fast.main()
    assert len(seen) == 1
    assert seen[0]["restore_model"].keywords["options"].workers == 3


@pytest.mark.parametrize("workers", ["1", "4"])
def test_formal_entry_callback_publishes_hash_verified_model(
        tmp_path, monkeypatch, transport, workers):
    payload, parts, calls = transport
    monkeypatch.setenv("H3_RESTORE_WORKERS", workers)

    def serial_download(*args):
        index = int(args[2].rsplit("-", 1)[1])
        calls.append(index)
        Path(args[3]).write_bytes(parts[index])

    def restore_with_callback(*, restore_model):
        restore_model(tmp_path / "models", "x/model.safetensors", len(payload),
                      hashlib.sha256(payload).hexdigest())

    monkeypatch.setattr(base, "run", serial_download)
    monkeypatch.setattr(base, "main", restore_with_callback)
    entry.main()
    output = tmp_path / "models/x/model.safetensors"
    assert output.read_bytes() == payload
    assert base.sha256(output) == hashlib.sha256(payload).hexdigest()
    assert sorted(calls) == list(range(len(parts)))
    assert not output.with_name(output.name + ".incomplete").exists()
