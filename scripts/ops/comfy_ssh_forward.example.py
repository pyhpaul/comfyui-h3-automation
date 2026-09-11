#!/usr/bin/env python3
"""Example TCP forwarder: 0.0.0.0:LISTEN → SSH → REMOTE Comfy (127.0.0.1:8188).

Deploy on **vm122** (not WSL). Copy to /tmp/comfy_ssh_forward.py or run in place.

Password: read from a file (chmod 600). Never commit the password file.

  export COMFY_GPU_SSH_HOST='....chenyu.cn'
  export COMFY_GPU_SSH_PORT=26301
  printf '%s\\n' 'SECRET' > /tmp/.comfy_gpu_ssh_pass && chmod 600 /tmp/.comfy_gpu_ssh_pass
  python comfy_ssh_forward.example.py 8190 /tmp/.comfy_gpu_ssh_pass
"""
from __future__ import annotations

import os
import select
import socket
import sys
import threading
from pathlib import Path

import paramiko

LISTEN_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8190
SSH_PASS = Path(sys.argv[2]).read_text(encoding="utf-8").strip() if len(sys.argv) > 2 else ""
SSH_HOST = os.environ.get("COMFY_GPU_SSH_HOST", "REPLACE_HOST.chenyu.cn")
SSH_PORT = int(os.environ.get("COMFY_GPU_SSH_PORT", "22"))
SSH_USER = os.environ.get("COMFY_GPU_SSH_USER", "root")
REMOTE = ("127.0.0.1", 8188)

_lock = threading.Lock()
_state: dict = {"transport": None, "client": None}


def ensure_transport():
    with _lock:
        t = _state["transport"]
        if t is not None and t.is_active():
            return t
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(
            SSH_HOST,
            port=SSH_PORT,
            username=SSH_USER,
            password=SSH_PASS,
            timeout=45,
            allow_agent=False,
            look_for_keys=False,
        )
        t = c.get_transport()
        t.set_keepalive(30)
        _state["client"] = c
        _state["transport"] = t
        print("ssh connected", SSH_HOST, SSH_PORT, flush=True)
        return t


def pipe(a, b):
    try:
        while True:
            r, _, x = select.select([a, b], [], [a, b], 120)
            if x or not r:
                break
            if a in r:
                data = a.recv(65535)
                if not data:
                    break
                b.sendall(data)
            if b in r:
                data = b.recv(65535)
                if not data:
                    break
                a.sendall(data)
    finally:
        for s in (a, b):
            try:
                s.close()
            except Exception:
                pass


def handle(client_sock):
    try:
        t = ensure_transport()
        chan = t.open_channel("direct-tcpip", REMOTE, client_sock.getpeername())
        if chan is None:
            client_sock.close()
            return
        pipe(client_sock, chan)
    except Exception as e:
        print("handle error", e, flush=True)
        try:
            client_sock.close()
        except Exception:
            pass


def main() -> None:
    if not SSH_PASS:
        sys.exit("need password file as argv[2]")
    if "REPLACE_HOST" in SSH_HOST:
        sys.exit("set COMFY_GPU_SSH_HOST / COMFY_GPU_SSH_PORT")
    ensure_transport()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", LISTEN_PORT))
    s.listen(64)
    print(f"listening 0.0.0.0:{LISTEN_PORT} -> {SSH_HOST}:{SSH_PORT} {REMOTE}", flush=True)
    while True:
        c, addr = s.accept()
        print("accept", addr, flush=True)
        threading.Thread(target=handle, args=(c,), daemon=True).start()


if __name__ == "__main__":
    main()
