"""Upload one finished H3 unit straight to Feiniu.

The archive folder gets four files: the mp4, the safetensors latent, prompt_h3.txt,
and run_meta.json. prompt_source.txt and prompt_audit.json stay off the share.
"""

from __future__ import annotations

import io
import os
import time
from pathlib import Path

HOST = "192.168.60.103"
SHARE = "ai短剧同步文件夹"
PASSFILE = Path(os.environ.get("H3_FEINIU_PASSFILE", "/home/linux_dev/.config/fnos/ai.pass"))
_KEEP = {"prompt_h3.txt", "run_meta.json"}
_SKIP = {"prompt_source.txt", "prompt_audit.json"}


def episode_code(episode: str) -> str:
    import re

    match = re.search(r"EP\d+", episode or "", re.I)
    if not match:
        raise RuntimeError(f"cannot parse episode from {episode!r}")
    return match.group(0).upper()


def remote_unit_dir(batch: str, episode: str, unit: str) -> str:
    return "\\".join(
        ["H3_comfyUI_5090", "archive", batch, episode_code(episode), unit.strip().upper()]
    )


def select_archive_files(files: dict[str, bytes]) -> list[tuple[str, bytes]]:
    chosen = [
        (name, payload)
        for name, payload in sorted(files.items())
        if name not in _SKIP and (name in _KEEP or name.endswith((".mp4", ".safetensors")))
    ]
    if len(chosen) != 4:
        names = [name for name, _payload in chosen]
        raise RuntimeError(f"archive file count is {len(chosen)}: {names}")
    return chosen


def _reader(payload: bytes):
    buffer = io.BytesIO(payload)

    def read(length: int) -> bytes:
        return buffer.read(length)

    return read


def _ensure_dir(smb, path: str) -> None:
    try:
        smb.createDirectory(SHARE, path)
    except Exception as exc:
        if exc.__class__.__name__ != "SessionError":
            raise


def _ensure_tree(smb, directory: str) -> None:
    parts = directory.split("\\")
    current = parts[0]
    for part in parts[1:]:
        current = f"{current}\\{part}"
        _ensure_dir(smb, current)


def _remote_sizes(smb, directory: str) -> dict[str, int]:
    sizes: dict[str, int] = {}
    try:
        items = smb.listPath(SHARE, directory + "\\*")
    except Exception as exc:
        if exc.__class__.__name__ != "SessionError":
            raise
        return {}
    for item in items:
        name = item.get_longname()
        if name in {".", ".."}:
            continue
        sizes[name] = int(item.get_filesize())
    return sizes


def connect_feiniu(passfile: Path | None = None):
    from impacket.smbconnection import SMBConnection

    password = (passfile or PASSFILE).read_text(encoding="utf-8").strip()
    smb = SMBConnection(HOST, HOST, sess_port=445)
    smb.login("ai", password)
    del password
    return smb


def archive_named_files(
    files: dict[str, bytes],
    *,
    batch: str,
    episode: str,
    unit: str,
    smb=None,
    connect=None,
    attempts: int = 6,
    sleep=time.sleep,
) -> str:
    chosen = select_archive_files(files)
    directory = remote_unit_dir(batch, episode, unit)
    owns_connection = smb is None
    current = smb if smb is not None else (connect or connect_feiniu)()
    try:
        _ensure_tree(current, directory)
        present = _remote_sizes(current, directory)
        for name, payload in chosen:
            if present.get(name) == len(payload):
                continue
            last_error: Exception | None = None
            for attempt in range(attempts):
                try:
                    current.putFile(SHARE, directory + "\\" + name, _reader(payload))
                    last_error = None
                    break
                except Exception as exc:
                    if exc.__class__.__name__ != "SessionError" or attempt + 1 == attempts:
                        raise
                    last_error = exc
                    sleep(20)
                    try:
                        current.close()
                    except Exception:
                        pass
                    current = (connect or connect_feiniu)()
                    owns_connection = True
                    _ensure_tree(current, directory)
            if last_error is not None:
                raise last_error
        checked = _remote_sizes(current, directory)
        for name, payload in chosen:
            if checked.get(name) != len(payload):
                raise RuntimeError(f"{unit} {name} size mismatch")
    finally:
        if owns_connection:
            try:
                current.close()
            except Exception:
                pass
    return directory
