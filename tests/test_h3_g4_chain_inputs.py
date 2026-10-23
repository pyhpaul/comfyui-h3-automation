import io
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
from h3_g4_chain_inputs import UNITS, archive_members, install_archive, verify_file


def make_archive(path: Path, extra_name: str | None = None) -> None:
    with tarfile.open(path, "w") as archive:
        for unit in UNITS:
            data = f"unit_id: {unit}\n".encode()
            info = tarfile.TarInfo(f"jobs/ep_units/EP04-H3-manual-v16-{unit}/job.yaml")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        if extra_name:
            info = tarfile.TarInfo(extra_name)
            info.size = 1
            archive.addfile(info, io.BytesIO(b"x"))


def test_archive_installs_only_expected_jobs(tmp_path: Path) -> None:
    archive = tmp_path / "jobs.tar"
    make_archive(archive)
    assert len(archive_members(archive)) == 3
    install_archive(archive, tmp_path / "runner")
    for unit in UNITS:
        assert (tmp_path / "runner/jobs/ep_units" /
                f"EP04-H3-manual-v16-{unit}/job.yaml").is_file()
    with pytest.raises(RuntimeError, match="already installed"):
        install_archive(archive, tmp_path / "runner")


@pytest.mark.parametrize("name", ["../escape", "jobs/ep_units/other/job.yaml",
                                   "/tmp/escape"])
def test_archive_rejects_unexpected_paths(tmp_path: Path, name: str) -> None:
    archive = tmp_path / "jobs.tar"
    make_archive(archive, name)
    with pytest.raises(RuntimeError, match="unsafe or unexpected"):
        archive_members(archive)


def test_verify_file_checks_size_and_hash(tmp_path: Path) -> None:
    path = tmp_path / "input.bin"
    path.write_bytes(b"frozen")
    verify_file(path, {"bytes": 6, "sha256":
                       "ffb304816a1090313e833215c08dae3d209cfad1ffd1f674f0909a2ae99e1394"})
    with pytest.raises(RuntimeError, match="frozen input mismatch"):
        verify_file(path, {"bytes": 7, "sha256": "bad"})
