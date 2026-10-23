import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
import colab_h3_g4_chain_host as host


def test_verify_unit_rejects_wrong_parent_or_unverified_archive(monkeypatch) -> None:
    receipt = {"state": "success", "archive_state": "verified", "session_id": "session",
               "label": "G4_U03", "unit": "U03", "parent_latent": host.PARENTS["U03"],
               "input_manifest_sha256": "manifest"}
    validation = {"unit": "U03", "latent": {"sha256": "latent"},
                  "video": {"sha256": "video"}}

    def remote(path: str) -> dict:
        return validation if path.endswith("validation.json") else receipt

    monkeypatch.setattr(host, "remote_json", remote)
    assert host.verify_unit("remote", "session", "U03", "manifest") == receipt
    receipt["archive_state"] = "pending"
    with pytest.raises(RuntimeError, match="incomplete or mismatched"):
        host.verify_unit("remote", "session", "U03", "manifest")
    receipt["archive_state"] = "verified"
    receipt["parent_latent"] = "wrong.safetensors"
    with pytest.raises(RuntimeError, match="incomplete or mismatched"):
        host.verify_unit("remote", "session", "U03", "manifest")


def test_verify_chain_inputs_requires_frozen_parent(monkeypatch) -> None:
    manifest = {"job_archive": {"sha256": "jobs"},
                "parent_latent": {"sha256": "parent"}}
    report = {"state": "ready", "units": list(host.PARENTS),
              "archive_sha256": "jobs", "parent_sha256": "parent",
              "parent_path": host.PARENTS["U03"]}
    monkeypatch.setattr(host, "remote_json", lambda path: report)
    host.verify_chain_inputs("remote", manifest)
    report["parent_sha256"] = "changed"
    with pytest.raises(RuntimeError, match="admission failed"):
        host.verify_chain_inputs("remote", manifest)


@pytest.mark.parametrize("workers", [1, 4])
def test_chain_uses_shared_bootstrap_before_formal_restore(workers):
    stages = host.chain_setup_stages("wheel-sha", "remote", workers)
    names = [stage[0] for stage in stages]
    assert names.index("identity") < names.index("bootstrap") < names.index("restore")
    restore = next(stage for stage in stages if stage[0] == "restore")
    assert restore[1] == host.SCRIPTS / "colab_h3_restore_entry.py"
    assert restore[3] == {"H3_RESTORE_WORKERS": str(workers)}
    assert names[-1] == "chain_inputs"
    assert stages[-1][3] == {"H3_G4_REMOTE": "remote"}


def test_chain_serial_option_remains_preflight_only(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(sys, "argv", ["chain-host", "--restore-workers", "1"])
    monkeypatch.setattr(host, "local_inputs", lambda: (tmp_path / "wheel", "sha", {}))
    monkeypatch.setattr(host, "sha256", lambda _: "manifest-sha")
    monkeypatch.setattr(host, "execute", lambda *args: pytest.fail("must not allocate"))
    host.main()
    report = json.loads(capsys.readouterr().out)
    assert report["restore_workers"] == 1
    assert report["paid_started"] is False
