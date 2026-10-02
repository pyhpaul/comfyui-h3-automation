"""Reattach a live assignment after Colab CLI prunes stale local metadata.

Run with the Python interpreter bundled with google-colab-cli. Never print
the short-lived runtime proxy token or URL.
"""

from __future__ import annotations

import argparse

from colab_cli.commands.session import spawn_keep_alive
from colab_cli.common import state
from colab_cli.state import SessionState


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session")
    parser.add_argument("endpoint")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    current = state.store.get(args.session)
    if current and not args.refresh:
        raise RuntimeError("local session metadata still exists; do not overwrite it")
    if args.refresh and (not current or current.endpoint != args.endpoint):
        raise RuntimeError("refresh requires matching existing local session metadata")
    matches = [item for item in state.client.list_assignments() if item.endpoint == args.endpoint]
    if len(matches) != 1:
        raise RuntimeError("expected exactly one live assignment for the endpoint")
    assignment = matches[0]
    proxy = assignment.runtime_proxy_info
    session = SessionState(name=args.session, token=proxy.token, url=proxy.url,
                           endpoint=assignment.endpoint, variant=assignment.variant.name,
                           accelerator=assignment.accelerator.value,
                           machine_shape=assignment.machine_shape.name,
                           kernel_id=current.kernel_id if current else None,
                           session_id=current.session_id if current else None,
                           keep_alive_pid=current.keep_alive_pid if current else None)
    state.store.add(session)
    if not current:
        session.keep_alive_pid = spawn_keep_alive(assignment.endpoint, args.session,
                                                 auth_provider=state.auth_provider,
                                                 config_path=state.store.path)
        state.store.add(session)
    print("REFRESHED" if current else "REATTACHED", args.session, assignment.endpoint, flush=True)


if __name__ == "__main__":
    main()
