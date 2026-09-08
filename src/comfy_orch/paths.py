from pathlib import Path


def project_root() -> Path:
    # package at src/comfy_orch → parents[2] is repo root when editable
    return Path(__file__).resolve().parents[2]


def templates_dir(root: Path | None = None) -> Path:
    return (root or project_root()) / "templates"


def runs_dir(root: Path | None = None) -> Path:
    return (root or project_root()) / "runs"


def outputs_dir(root: Path | None = None) -> Path:
    return (root or project_root()) / "outputs"
