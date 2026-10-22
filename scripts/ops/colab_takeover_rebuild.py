#!/usr/bin/env python3
"""Rebuild a lost colab-cli session handle from the server side (takeover).

Verified 2026-10-22 (see runs/colab_takeover_test_20261022.md and
docs/ops/2026-10-21-colab-session-loss-and-guard.md): after the local
~/.config/colab-cli/sessions.json is lost, the account-side assignment
keeps billing. list_assignments() returns the assignment's CURRENT
runtimeProxyInfo (a fresh token — the old one never comes back), so a
SessionState can be rebuilt by hand and the same VM re-adopted:
exec and stop then work by name again.

Run with the colab-cli interpreter (same requirement as
colab_unassign.py), e.g.:
  ~/.local/share/uv/tools/google-colab-cli/bin/python3 \
    scripts/ops/colab_takeover_rebuild.py <session-name> \
    [--backup <sessions_backup.json>] [--endpoint <endpoint>]

Matching: --endpoint wins; else the endpoint recorded in --backup for
<session-name>; else, if exactly one assignment is active, that one.
kernel_id/session_id are reused from --backup when present; without a
backup they are left None and exec will start a fresh kernel on the
same VM (filesystem survives, kernel state does not — untested branch,
plan accordingly). Time-box any takeover attempt: if the VM has been
ownerless for long it may already be recycled; on failure fall back to
colab_unassign.py immediately instead of lingering on a billing VM.

Never prints tokens (SHA-256 fingerprints only).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from colab_cli.auth import AuthProvider, get_credentials
from colab_cli.client import Client, Prod
from colab_cli.commands.session import spawn_keep_alive
from colab_cli.state import SessionState, StateStore


def fp(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:12] if token else "none"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("name", help="session name to (re)register locally")
    ap.add_argument("--backup", type=Path,
                    help="pre-loss sessions.json backup (endpoint/kernel source)")
    ap.add_argument("--endpoint", help="assignment endpoint to adopt")
    args = ap.parse_args()

    orig = {}
    if args.backup:
        backup = json.loads(args.backup.read_text())
        orig = backup.get(args.name) or {}
        if not orig and not args.endpoint:
            print(f"REBUILD_FAIL backup has no {args.name!r}, keys={list(backup)}")
            return 3
    endpoint = args.endpoint or orig.get("endpoint")

    creds = get_credentials(os.path.expanduser("~/.colab-cli-oauth-config.json"),
                            provider=AuthProvider.OAUTH2)
    client = Client(Prod(), creds)
    assignments = client.list_assignments()
    print(f"LIST_ASSIGNMENTS count={len(assignments)}")
    for a in assignments:
        info = a.runtime_proxy_info
        host = info.url.split("/")[2] if "://" in (info.url or "") else (info.url or "")[:30]
        print(f" assignment endpoint={a.endpoint} accelerator={a.accelerator.value} "
              f"variant={a.variant.name} machine_shape={a.machine_shape.name} "
              f"token_expires_in={info.token_expires_in_seconds} url_host={host}")

    if endpoint:
        targets = [a for a in assignments if a.endpoint == endpoint]
    elif len(assignments) == 1:
        targets = list(assignments)
    else:
        targets = []
    print(f"MATCH count={len(targets)}")
    if len(targets) != 1:
        print("REBUILD_FAIL cannot uniquely match assignment "
              "(pass --endpoint or --backup)")
        return 4
    a = targets[0]
    info = a.runtime_proxy_info
    new_tok, old_tok = info.token, orig.get("token", "")
    print(f"TOKEN old_fp={fp(old_tok)} new_fp={fp(new_tok)} same={new_tok == old_tok} "
          f"old_len={len(old_tok)} new_len={len(new_tok)}")
    print(f"URL same={info.url == orig.get('url')} "
          f"orig_kernel_id_present={bool(orig.get('kernel_id'))} "
          f"orig_session_id_present={bool(orig.get('session_id'))}")

    state = SessionState(
        name=args.name, token=new_tok, url=info.url, endpoint=a.endpoint,
        variant=a.variant.name, accelerator=a.accelerator.value,
        machine_shape=a.machine_shape.name,
        kernel_id=orig.get("kernel_id"), session_id=orig.get("session_id"))
    store = StateStore()
    store.add(state)
    print("SESSIONSTATE_WRITTEN")
    pid = spawn_keep_alive(a.endpoint, args.name)
    state.keep_alive_pid = pid
    store.add(state)
    print(f"KEEP_ALIVE_SPAWNED pid={pid}")
    print("REBUILD_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
