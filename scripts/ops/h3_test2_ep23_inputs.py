"""Install the accepted Test2 EP02/EP03 jobs and nine-image runtime overlay."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

from h3_test2_ep23_contract import UNITS, job_name


CONTENT = Path("/content")
RUNNER = CONTENT / "h3-runner"
MANIFEST = CONTENT / "test2-ep23-input-manifest.json"
PATCH = CONTENT / "test2-ep23-api9.tar.gz"
CONFIG = CONTENT / "rclone.conf"
RCLONE = CONTENT / "rclone"
PATCH_SHA256 = "4c774aa0f6299ad2142712bf1b47845ea0f4ef567a890ad41f6603beb80b4a63"
PATCH_MEMBERS = {
    "src/comfy_orch/prompt_wire.py", "src/comfy_orch/ui_bind.py",
    "templates/yz_h3_ep_unit/bindings.yaml",
    "templates/yz_h3_ep_unit/manifest.schema.yaml",
    "templates/yz_h3_ep_unit/workflow_api.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_members(archive: Path, expected_roots: set[str] | None = None) -> list[tarfile.TarInfo]:
    with tarfile.open(archive) as package:
        members = package.getmembers()
    for member in members:
        name = PurePosixPath(member.name)
        if name.is_absolute() or ".." in name.parts or not (member.isfile() or member.isdir()):
            raise RuntimeError(f"unsafe archive member: {member.name}")
        if expected_roots is not None:
            if len(name.parts) < 3:
                if member.name not in {"jobs", "jobs/ep_units"} or not member.isdir():
                    raise RuntimeError(f"unexpected job member: {member.name}")
            elif "/".join(name.parts[:3]) not in expected_roots:
                raise RuntimeError(f"unexpected job member: {member.name}")
    return members


def install_jobs(archive: Path, expected_roots: set[str]) -> None:
    members = safe_members(archive, expected_roots)
    names = {member.name for member in members}
    if any(f"{root}/job.yaml" not in names for root in expected_roots):
        raise RuntimeError("accepted job archive is missing a unit")
    if any((RUNNER / root).exists() for root in expected_roots):
        raise RuntimeError("selected Test2 jobs already installed; inspect before retry")
    with tarfile.open(archive) as package:
        package.extractall(RUNNER, members=members, filter="data")


def install_patch() -> None:
    if sha256(PATCH) != PATCH_SHA256:
        raise RuntimeError("nine-image runtime patch hash mismatch")
    members = safe_members(PATCH)
    if {member.name for member in members if member.isfile()} != PATCH_MEMBERS:
        raise RuntimeError("nine-image patch members changed")
    backup = CONTENT / "h3-runner-api6-backup"
    backup.mkdir(exist_ok=False)
    for relative in PATCH_MEMBERS:
        original = RUNNER / relative
        target = backup / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(original.read_bytes())
    with tarfile.open(PATCH) as package:
        package.extractall(RUNNER, members=members, filter="data")
    with tarfile.open(PATCH) as package:
        for member in members:
            if member.isfile():
                extracted = package.extractfile(member)
                if extracted is None or (RUNNER / member.name).read_bytes() != extracted.read():
                    raise RuntimeError(f"runtime patch extraction failed: {member.name}")


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if (
        manifest.get("schema_version") != 1
        or manifest.get("episodes") != ["EP02", "EP03"]
        or manifest.get("accepted_independent_starts")
        != {"EP02": ["U01", "U02", "U04", "U06"], "EP03": ["U01"]}
    ):
        raise RuntimeError("unexpected accepted Test2 EP02/EP03 manifest")
    record = manifest["job_archive"]
    archive = CONTENT / "test2-ep23-jobs.tar.gz"
    subprocess.run([str(RCLONE), "copyto", record["remote"], str(archive),
                    "--config", str(CONFIG), "--retries", "3"],
                   check=True, timeout=600)
    if (archive.stat().st_size != record["bytes_local_and_remote"]
            or sha256(archive) != record["sha256_local"]):
        raise RuntimeError("accepted jobs differ from frozen local SHA-256")
    expected_roots = {f"jobs/ep_units/{job_name(ep, unit)}"
                      for ep, units in UNITS.items() for unit in units}
    install_jobs(archive, expected_roots)
    install_patch()
    report = {
        "state": "ready", "episodes": {episode: list(units) for episode, units in UNITS.items()},
        "archive_sha256": record["sha256_local"],
        "runtime_api9_sha256": PATCH_SHA256,
        "source_zip_sha256": manifest["source_zip_sha256"],
    }
    output = CONTENT / "test2-ep23-inputs.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    remote = os.environ.get("H3_TEST2_REMOTE")
    if remote:
        subprocess.run([str(RCLONE), "copyto", str(output), f"{remote}/inputs.json",
                        "--config", str(CONFIG)], check=True, timeout=120)
    print("TEST2_EP23_INPUTS_READY", json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
