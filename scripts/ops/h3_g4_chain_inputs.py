"""Verify and install frozen EP04 U03-U05 inputs on an existing Colab restore."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tarfile
from pathlib import Path, PurePosixPath


CONTENT = Path("/content")
CONFIG = CONTENT / "rclone.conf"
RCLONE = CONTENT / "rclone"
RUNNER = CONTENT / "h3-runner"
COMFY = CONTENT / "h3-rental/ComfyUI"
MANIFEST = CONTENT / "g4-chain-input-manifest.json"
UNITS = ("U03", "U04", "U05")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_file(path: Path, record: dict) -> None:
    if path.stat().st_size != record["bytes"] or sha256(path) != record["sha256"]:
        raise RuntimeError(f"frozen input mismatch: {path}")


def archive_members(archive: Path) -> list[tarfile.TarInfo]:
    roots = {f"jobs/ep_units/EP04-H3-manual-v16-{unit}" for unit in UNITS}
    with tarfile.open(archive) as package:
        members = package.getmembers()
    for member in members:
        name = PurePosixPath(member.name)
        if (name.is_absolute() or ".." in name.parts or not (member.isfile() or member.isdir())
                or len(name.parts) < 3 or "/".join(name.parts[:3]) not in roots):
            raise RuntimeError(f"unsafe or unexpected archive member: {member.name}")
    for root in roots:
        if f"{root}/job.yaml" not in {member.name for member in members}:
            raise RuntimeError(f"missing frozen job: {root}")
    return members


def install_archive(archive: Path, runner: Path) -> None:
    members = archive_members(archive)
    for unit in UNITS:
        if (runner / "jobs/ep_units" / f"EP04-H3-manual-v16-{unit}").exists():
            raise RuntimeError(f"{unit} already installed; refusing to overwrite")
    with tarfile.open(archive) as package:
        package.extractall(runner, members=members, filter="data")


def fetch(record: dict, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise RuntimeError(f"refusing to overwrite input: {destination}")
    subprocess.run([str(RCLONE), "copyto", record["remote"], str(destination),
                    "--config", str(CONFIG), "--retries", "3"], check=True, timeout=300)
    verify_file(destination, record)


def main() -> None:
    manifest = json.loads(MANIFEST.read_text())
    if (manifest.get("schema_version") != 1 or manifest.get("units") != list(UNITS)
            or manifest.get("episode") != "EP04-H3-manual-v16"):
        raise RuntimeError("unexpected G4 chain input manifest")
    archive = CONTENT / "g4-chain-jobs.tar"
    fetch(manifest["job_archive"], archive)
    archive_members(archive)
    parent = COMFY / "output" / manifest["parent_latent"]["output_relative_path"]
    if not parent.is_relative_to(COMFY / "output"):
        raise RuntimeError("parent latent path escapes Comfy output")
    fetch(manifest["parent_latent"], parent)
    install_archive(archive, RUNNER)
    report = {"state": "ready", "units": list(UNITS),
              "archive_sha256": manifest["job_archive"]["sha256"],
              "parent_sha256": manifest["parent_latent"]["sha256"],
              "parent_path": manifest["parent_latent"]["output_relative_path"]}
    report_path = CONTENT / "g4-chain-inputs.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    remote = os.environ.get("H3_G4_REMOTE")
    if remote:
        subprocess.run([str(RCLONE), "copyto", str(report_path),
                        f"{remote}/chain-inputs.json", "--config", str(CONFIG)],
                       check=True, timeout=120)
    print("G4_CHAIN_INPUTS_READY", json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
