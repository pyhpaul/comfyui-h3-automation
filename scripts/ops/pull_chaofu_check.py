#!/usr/bin/env python3
"""Pull existing Chaofu renders from Feiniu for dialogue/scene checking.

SMB: 192.168.60.103 share 'ai短剧同步文件夹', user 'ai',
password from /home/linux_dev/.config/fnos/ai.pass (never printed).
Downloads only *-audio.mp4 per requested EP/U unit into an output dir.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

from impacket.smbconnection import SMBConnection

SERVER = "192.168.60.103"
SHARE = "ai短剧同步文件夹"
USER = "ai"
PASSFILE = "/home/linux_dev/.config/fnos/ai.pass"
ARCHIVE = "H3_comfyUI_5090/archive/潮缚（10.16）"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--units", nargs="+", required=True, help="e.g. EP06-U04")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    password = pathlib.Path(PASSFILE).read_text().strip()
    conn = SMBConnection(SERVER, SERVER, sess_port=445, timeout=60)
    conn.login(USER, password)
    out_root = pathlib.Path(args.out)
    failures = []
    for unit in args.units:
        ep, uu = unit.split("-")
        # QC renamed some unit dirs with problem annotations, e.g.
        # 'U04（第一小段人物对白不一致）' — match by unit prefix.
        try:
            # Episode dir may also be annotated, e.g. 'EP24（ 场景不是黑夜，整集重出）'.
            base_entries = conn.listPath(SHARE, ARCHIVE + "/*")
            ep_dirs = [
                e.get_longname()
                for e in base_entries
                if e.is_directory() and e.get_longname().startswith(ep)
            ]
            if not ep_dirs:
                failures.append(f"{unit}: no episode dir starting {ep}")
                continue
            ep = sorted(ep_dirs)[0]
            ep_entries = conn.listPath(SHARE, f"{ARCHIVE}/{ep}/*")
            unit_dirs = [
                e.get_longname()
                for e in ep_entries
                if e.is_directory() and e.get_longname().startswith(uu)
            ]
            if not unit_dirs:
                failures.append(f"{unit}: no dir starting {uu} under {ep}")
                continue
            remote_dir = f"{ARCHIVE}/{ep}/{sorted(unit_dirs)[0]}"
            entries = conn.listPath(SHARE, remote_dir + "/*")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{unit}: list failed {exc}")
            continue
        mp4s = [
            e.get_longname()
            for e in entries
            if e.get_longname().endswith("-audio.mp4")
        ]
        if not mp4s:
            failures.append(f"{unit}: no -audio.mp4 in {remote_dir}")
            continue
        name = sorted(mp4s)[-1]
        dest = out_root / unit
        dest.mkdir(parents=True, exist_ok=True)
        local = dest / name
        with open(local, "wb") as fh:
            conn.getFile(SHARE, f"{remote_dir}/{name}", fh.write)
        print(f"OK {unit} {name} {local.stat().st_size} bytes")
    conn.logoff()
    for f in failures:
        print("FAIL", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
