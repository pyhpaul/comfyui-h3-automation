#!/usr/bin/env python3
"""Stage parent AV latents for unit-only Chaofu re-renders.

Downloads the latest latent of each parent unit from the Feiniu archive
(潮缚（10.16）) and uploads it to the rental pod's
ComfyUI/output/h3_context/ so run_ep_units_profiled.py can resume the
motion_latent chain with --parent-latent h3_context/<file>.

Pod SSH password read from COMFY_GPU_SSH_PASSFILE; Feiniu password from
/home/linux_dev/.config/fnos/ai.pass. Neither is printed.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys

import paramiko
from impacket.smbconnection import SMBConnection

SHARE = "ai短剧同步文件夹"
ARCHIVE = "H3_comfyUI_5090/archive/潮缚（10.16）"
POD_DIR = "/root/autodl-tmp/ComfyUI/output/h3_context"


def resolve_dir(conn: SMBConnection, parent: str, prefix: str) -> str:
    entries = conn.listPath(SHARE, parent + "/*")
    hits = [
        e.get_longname()
        for e in entries
        if e.is_directory() and e.get_longname().startswith(prefix)
    ]
    if not hits:
        raise SystemExit(f"no dir {prefix}* under {parent}")
    return sorted(hits)[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parents", nargs="+", required=True,
                    help="parent units e.g. EP06-U03")
    ap.add_argument("--cache", type=pathlib.Path, required=True)
    args = ap.parse_args()

    feiniu_pw = pathlib.Path(
        "/home/linux_dev/.config/fnos/ai.pass").read_text().strip()
    conn = SMBConnection("192.168.60.103", "192.168.60.103",
                         sess_port=445, timeout=120)
    conn.login("ai", feiniu_pw)

    host = os.environ["COMFY_GPU_SSH_HOST"]
    port = int(os.environ["COMFY_GPU_SSH_PORT"])
    pod_pw = pathlib.Path(
        os.environ["COMFY_GPU_SSH_PASSFILE"]).read_text().strip()
    pod = paramiko.SSHClient()
    pod.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    pod.connect(host, port=port, username="root", password=pod_pw,
                timeout=30, allow_agent=False, look_for_keys=False)
    sftp = pod.open_sftp()
    try:
        sftp.mkdir(POD_DIR)
    except OSError:
        pass

    args.cache.mkdir(parents=True, exist_ok=True)
    for unit in args.parents:
        ep, uu = unit.split("-")
        ep_dir = resolve_dir(conn, ARCHIVE, ep)
        unit_dir = resolve_dir(conn, f"{ARCHIVE}/{ep_dir}", uu)
        remote = f"{ARCHIVE}/{ep_dir}/{unit_dir}"
        entries = conn.listPath(SHARE, remote + "/*")
        latents = sorted(
            e.get_longname() for e in entries
            if e.get_longname().endswith(".safetensors"))
        if not latents:
            print(f"{unit}: NO LATENT in {remote}")
            continue
        name = latents[-1]
        local = args.cache / name
        if not local.exists():
            with open(local, "wb") as fh:
                conn.getFile(SHARE, f"{remote}/{name}", fh.write)
        sftp.put(str(local), f"{POD_DIR}/{name}")
        print(f"{unit} -> h3_context/{name} ({local.stat().st_size} B)")
    sftp.close()
    pod.close()
    conn.logoff()
    return 0


if __name__ == "__main__":
    sys.exit(main())
