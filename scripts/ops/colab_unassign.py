#!/usr/bin/env python3
"""Unassign Colab runtimes server-side, bypassing the local session registry.

Why this exists: google-colab-cli keeps the name->runtime map in
~/.config/colab-cli/sessions.json. When an exec fails with 404/401 the CLI
decides the session is "lost" and wipes that map; afterwards every name-based
command (including `colab stop`) answers "not found" while the account-level
assignment keeps billing. The backend still lists the assignment, and
Client.unassign(endpoint) stops it. This script drives colab_cli's own
client, so it must run with the CLI's interpreter:

  ~/.local/share/uv/tools/google-colab-cli/bin/python3 \
      scripts/ops/colab_unassign.py [--endpoint-frag FRAG] [--execute]

Without --execute it only lists. With --execute it unassigns only when the
fragment matches exactly one assignment (or, without a fragment, when there
is exactly one assignment at all). It never bulk-unassigns.
"""
import os
import sys

from colab_cli.auth import AuthProvider, get_credentials
from colab_cli.client import Client, Prod


def main() -> int:
    frag = ""
    execute = False
    args = sys.argv[1:]
    while args:
        a = args.pop(0)
        if a == "--endpoint-frag":
            frag = args.pop(0)
        elif a == "--execute":
            execute = True
        else:
            print(f"unknown arg {a!r}")
            return 2
    creds = get_credentials(
        os.path.expanduser("~/.colab-cli-oauth-config.json"),
        provider=AuthProvider.OAUTH2,
    )
    client = Client(Prod(), creds)
    assignments = client.list_assignments()
    print(f"server assignments: {len(assignments)}")
    for a in assignments:
        print(" -", a.endpoint)
    if not execute:
        print("LIST_ONLY (pass --execute to unassign)")
        return 0
    targets = [a for a in assignments if frag in str(a.endpoint)] if frag \
        else list(assignments)
    if len(targets) != 1:
        print(f"REFUSE targets={len(targets)} frag={frag!r}")
        return 1
    endpoint = targets[0].endpoint
    print("unassigning", endpoint)
    client.unassign(endpoint)
    after = client.list_assignments()
    print(f"after: {len(after)} assignments")
    print("UNASSIGNED_OK" if not after else "STILL_ACTIVE")
    return 0 if not after else 1


if __name__ == "__main__":
    raise SystemExit(main())
