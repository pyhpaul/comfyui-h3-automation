import os
from pathlib import Path
import typer
from comfy_orch.client import ComfyClient
from comfy_orch.runner import submit_job
from comfy_orch.status import read_status
from comfy_orch.paths import runs_dir, project_root
from comfy_orch.errors import ComfyOrchError

app = typer.Typer(help="Remote ComfyUI orchestration", no_args_is_help=True)

def _base_url() -> str:
    url = os.environ.get("COMFY_BASE_URL", "").strip()
    if not url:
        raise typer.BadParameter("set COMFY_BASE_URL")
    return url

@app.command()
def doctor() -> None:
    """Check connectivity to ComfyUI via COMFY_BASE_URL."""
    c = ComfyClient(_base_url())
    try:
        stats = c.system_stats()
    except ComfyOrchError as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1) from e
    finally:
        c.close()
    typer.echo(stats)

@app.command()
def submit(job_dir: Path) -> None:
    """Validate, run, and collect outputs for a job directory."""
    try:
        job_id = submit_job(job_dir, base_url=_base_url(), root=project_root())
    except ComfyOrchError as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1) from e
    typer.echo(job_id)

@app.command()
def status(job_id: str) -> None:
    """Show local run status for a job_id."""
    path = runs_dir() / job_id / "status.json"
    if not path.is_file():
        typer.secho("not found", fg=typer.colors.RED)
        raise typer.Exit(1)
    st = read_status(path)
    typer.echo(f"{st.state} prompt_id={st.prompt_id} outputs={st.outputs}")

if __name__ == "__main__":
    app()
