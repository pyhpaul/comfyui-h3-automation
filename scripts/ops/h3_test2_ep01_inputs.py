"""Install the frozen Test2 EP01 jobs after the standard Colab G4 restore."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

from h3_test2_ep01_contract import UNITS, job_name


CONTENT = Path("/content")
CONFIG = CONTENT / "rclone.conf"
RCLONE = CONTENT / "rclone"
RUNNER = CONTENT / "h3-runner"
MANIFEST = CONTENT / "test2-ep01-input-manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_file(path: Path, record: dict) -> None:
    if path.stat().st_size != record["bytes"] or sha256(path) != record["sha256"]:
        raise RuntimeError(f"frozen Test2 input mismatch: {path}")


def archive_members(archive: Path) -> list[tarfile.TarInfo]:
    roots = {f"jobs/ep_units/{job_name(unit)}" for unit in UNITS}
    with tarfile.open(archive) as package:
        members = package.getmembers()
    names = {member.name for member in members}
    for member in members:
        name = PurePosixPath(member.name)
        root = "/".join(name.parts[:3])
        if (
            name.is_absolute()
            or ".." in name.parts
            or not (member.isfile() or member.isdir())
            or len(name.parts) < 3
            or root not in roots
        ):
            raise RuntimeError(f"unsafe or unexpected Test2 archive member: {member.name}")
    if any(f"{root}/job.yaml" not in names for root in roots):
        raise RuntimeError("frozen Test2 archive is missing a selected job")
    return members


def install_archive(archive: Path, runner: Path) -> None:
    members = archive_members(archive)
    for unit in UNITS:
        destination = runner / "jobs/ep_units" / job_name(unit)
        if destination.exists():
            raise RuntimeError(f"{unit} already installed; refusing to overwrite")
    with tarfile.open(archive) as package:
        package.extractall(runner, members=members, filter="data")


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if (
        manifest.get("schema_version") != 1
        or manifest.get("units") != list(UNITS)
        or manifest.get("independent_starts") != ["U01", "U05"]
        or manifest.get("episode") != "EP01-测试2-v1"
    ):
        raise RuntimeError("unexpected Test2 EP01 input manifest")
    record = manifest["job_archive"]
    archive = CONTENT / "test2-ep01-jobs-v1.tar"
    subprocess.run(
        [str(RCLONE), "copyto", record["remote"], str(archive),
         "--config", str(CONFIG), "--retries", "3"],
        check=True, timeout=600,
    )
    verify_file(archive, record)
    install_archive(archive, RUNNER)
    report = {"state": "ready", "units": list(UNITS),
              "archive_sha256": record["sha256"],
              "source_zip_sha256": manifest["source_zip_sha256"]}
    report_path = CONTENT / "test2-ep01-inputs.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    remote = os.environ.get("H3_TEST2_REMOTE")
    if remote:
        subprocess.run(
            [str(RCLONE), "copyto", str(report_path), f"{remote}/inputs.json",
             "--config", str(CONFIG)],
            check=True, timeout=120,
        )
    print("TEST2_EP01_INPUTS_READY", json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
