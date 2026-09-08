from pathlib import Path
import pytest
from comfy_orch.manifest import load_and_validate_job
from comfy_orch.errors import ValidationError

FIXTURES = Path(__file__).parent / "fixtures"

def test_missing_file_raises(tmp_path: Path):
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "job.yaml").write_text(
        "template: demo\nfields:\n  prompt: hello\n  first_frame: assets/missing.png\n",
        encoding="utf-8",
    )
    schema = FIXTURES / "templates" / "demo" / "manifest.schema.yaml"
    with pytest.raises(ValidationError, match="first_frame"):
        load_and_validate_job(job_dir, schema_path=schema)

def test_ok_job_returns_payload(tmp_path: Path):
    job_dir = tmp_path / "job"
    (job_dir / "assets").mkdir(parents=True)
    (job_dir / "assets" / "ref.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (job_dir / "job.yaml").write_text(
        "template: demo\nfields:\n  prompt: hello\n  first_frame: assets/ref.png\n",
        encoding="utf-8",
    )
    schema = FIXTURES / "templates" / "demo" / "manifest.schema.yaml"
    job = load_and_validate_job(job_dir, schema_path=schema)
    assert job.template == "demo"
    assert job.fields["prompt"] == "hello"
    assert job.resolve_path("first_frame").is_file()
