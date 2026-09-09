import os
from pathlib import Path

import typer

from comfy_orch.client import ComfyClient
from comfy_orch.errors import ComfyOrchError
from comfy_orch.inbox import process_inbox_once, watch_inbox
from comfy_orch.paths import project_root, runs_dir
from comfy_orch.runner import submit_job
from comfy_orch.status import read_status

app = typer.Typer(help="Remote ComfyUI orchestration", no_args_is_help=True)


def _base_url() -> str:
    url = os.environ.get("COMFY_BASE_URL", "").strip()
    if not url:
        raise typer.BadParameter("set COMFY_BASE_URL")
    return url


def _client_id(explicit: str | None) -> str | None:
    if explicit and explicit.strip():
        return explicit.strip()
    env = os.environ.get("COMFY_CLIENT_ID", "").strip()
    return env or None


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
def submit(
    job_dir: Path,
    client_id: str | None = typer.Option(
        None, "--client-id", help="ComfyUI client_id for WS progress alignment"
    ),
) -> None:
    """Validate, run, and collect outputs for a job directory."""
    try:
        job_id = submit_job(
            job_dir,
            base_url=_base_url(),
            root=project_root(),
            client_id=_client_id(client_id),
        )
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


@app.command()
def watch(
    inbox: Path = typer.Option(
        Path("inbox"),
        help="Directory to scan for job folders containing job.yaml",
    ),
    interval: float = typer.Option(5.0, help="Poll interval seconds"),
    once: bool = typer.Option(False, help="Process one scan then exit"),
    client_id: str | None = typer.Option(
        None, "--client-id", help="ComfyUI client_id for WS progress alignment"
    ),
) -> None:
    """Watch inbox for jobs; move to inbox/.done or inbox/.failed after submit."""
    root = project_root()
    inbox_path = inbox if inbox.is_absolute() else root / inbox
    resolved_client_id = _client_id(client_id)
    try:
        if once:
            results = process_inbox_once(
                inbox_path,
                base_url=_base_url(),
                root=root,
                client_id=resolved_client_id,
            )
            for moved, job_id, err in results:
                if err:
                    typer.secho(f"FAILED {moved.name}: {err}", fg=typer.colors.RED)
                else:
                    typer.echo(f"OK {moved.name} -> {job_id}")
            if not results:
                typer.echo("no jobs")
        else:
            typer.echo(f"watching {inbox_path} every {interval}s")
            watch_inbox(
                inbox_path,
                base_url=_base_url(),
                root=root,
                interval=interval,
                once=False,
                client_id=resolved_client_id,
            )
    except ComfyOrchError as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
