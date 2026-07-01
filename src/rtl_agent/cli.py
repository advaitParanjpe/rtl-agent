from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from rtl_agent.artifacts import RunStore
from rtl_agent.config import load_config
from rtl_agent.execution import CommandRunner

app = typer.Typer(
    help="Deterministic orchestration foundation for RTL engineering workflows.",
    no_args_is_help=True,
)


def _print_json(data: object) -> None:
    typer.echo(json.dumps(data, indent=2, sort_keys=True))


@app.command()
def init(
    path: Annotated[Path, typer.Option(help="Directory where .rtl-agent is created.")] = Path("."),
) -> None:
    """Create the local artifact directory."""
    target = (path / ".rtl-agent" / "runs").resolve()
    target.mkdir(parents=True, exist_ok=True)
    typer.echo(f"initialized {target}")


@app.command("inspect-config")
def inspect_config(
    config: Annotated[Path, typer.Option("--config", "-c", help="Path to rtl-agent YAML config.")],
) -> None:
    """Load configuration and print a sanitized summary."""
    try:
        loaded = load_config(config)
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_json(
        {
            "schema_version": loaded.schema_version,
            "repository_root": str(loaded.repository_root),
            "run_root": str(loaded.run_root),
            "commands": sorted(loaded.commands),
            "timeout_seconds": loaded.execution.timeout_seconds,
        }
    )


@app.command("run-command")
def run_command(
    config: Annotated[Path, typer.Option("--config", "-c", help="Path to rtl-agent YAML config.")],
    command: Annotated[str, typer.Option("--command", help="Configured command name.")],
) -> None:
    """Run a configured named command and write run artifacts."""
    try:
        loaded = load_config(config)
        run_store = RunStore(loaded.run_root)
        run_store.create()
        result = CommandRunner(loaded, run_store).run_named(command)
    except (KeyError, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_json(
        {
            "run_id": run_store.run_id,
            "command_id": result.command_id,
            "command_name": result.command_name,
            "status": result.status,
            "exit_code": result.exit_code,
            "result_path": str(run_store.run_dir / "commands" / result.command_id / "result.json"),
            "stdout_path": str(result.stdout_path),
            "stderr_path": str(result.stderr_path),
        }
    )
    if result.exit_code != 0:
        raise typer.Exit(result.exit_code if result.exit_code is not None else 1)


def main() -> None:
    app()
