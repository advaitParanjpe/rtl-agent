from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from rtl_agent.artifacts import RunStore
from rtl_agent.config import load_config
from rtl_agent.discovery import DiscoveryError, discover_repository, write_repository_map
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


@app.command("inspect-repo")
def inspect_repo(
    repo: Annotated[Path, typer.Option("--repo", help="Repository root to inspect.")],
    output: Annotated[Path, typer.Option("--output", help="Path for repository-map JSON.")],
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Optional rtl-agent YAML config for discovery limits."),
    ] = None,
) -> None:
    """Inspect an RTL repository and write a structured repository map."""
    try:
        loaded = load_config(config) if config else None
        discovery_config = loaded.discovery if loaded else None
        repository_map = discover_repository(repo, discovery_config)
        write_repository_map(repository_map, output)
    except (DiscoveryError, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_discovery_summary(repository_map, output)


@app.command("discover")
def discover(
    config: Annotated[Path, typer.Option("--config", "-c", help="Path to rtl-agent YAML config.")],
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Optional path for repository-map JSON."),
    ] = None,
) -> None:
    """Inspect the configured repository and write discovery run artifacts."""
    try:
        loaded = load_config(config)
        loaded.assert_working_path_allowed(loaded.repository_root)
        run_store = RunStore(loaded.run_root)
        run_store.create()
        repository_map = discover_repository(loaded.repository_root, loaded.discovery)
        discovery_output = output or (run_store.run_dir / "discovery" / "repository-map.json")
        write_repository_map(repository_map, discovery_output)
        run_store.append_event(
            "repository_discovered",
            {
                "repository_root": str(repository_map.repository_root),
                "repository_map": str(discovery_output),
                "files_indexed": repository_map.scan_statistics.files_indexed,
            },
        )
    except (DiscoveryError, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_discovery_summary(repository_map, discovery_output, run_id=run_store.run_id)


def _print_discovery_summary(
    repository_map: object, output: Path, run_id: str | None = None
) -> None:
    from rtl_agent.repository_map import RepositoryMap

    assert isinstance(repository_map, RepositoryMap)
    summary = {
        "schema_version": repository_map.schema_version,
        "repository_root": str(repository_map.repository_root),
        "output": str(output),
        "files_indexed": repository_map.scan_statistics.files_indexed,
        "declarations": sum(
            len(record.source.declarations) for record in repository_map.files if record.source
        ),
        "commands": len(repository_map.commands),
        "warnings": len(repository_map.warnings),
    }
    if run_id:
        summary["run_id"] = run_id
    _print_json(summary)


def main() -> None:
    app()
