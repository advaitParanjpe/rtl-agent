from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from rtl_agent.artifacts import RunStore
from rtl_agent.config import load_config
from rtl_agent.discovery import DiscoveryError, discover_repository, write_repository_map
from rtl_agent.execution import CommandRunner
from rtl_agent.implementation import (
    ImplementationError,
    run_bounded_implementation,
    write_implementation_report,
)
from rtl_agent.issues import IssueParsingError, parse_issue_file, write_task_contract
from rtl_agent.review import ReviewError, review_implementation, write_review_report
from rtl_agent.triage import TriageError, triage_command_result, write_triage_report
from rtl_agent.verification_strength_service import (
    VerificationStrengthError,
    assess_verification_strength,
    write_verification_strength_report,
)

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


@app.command("parse-issue")
def parse_issue(
    issue: Annotated[Path, typer.Option("--issue", help="Markdown or text issue file.")],
    output: Annotated[Path, typer.Option("--output", help="Path for task-contract JSON.")],
    repository_map: Annotated[
        Path | None,
        typer.Option(
            "--repository-map", help="Optional repository-map JSON for context validation."
        ),
    ] = None,
) -> None:
    """Parse an explicit issue into a deterministic task contract."""
    try:
        contract = parse_issue_file(issue, repository_map)
        write_task_contract(contract, output)
    except IssueParsingError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_task_contract_summary(contract, output)


@app.command("implement-task")
def implement_task(
    config: Annotated[Path, typer.Option("--config", "-c", help="Path to rtl-agent YAML config.")],
    task_contract: Annotated[Path, typer.Option("--task-contract", help="Task-contract JSON.")],
    repository_map: Annotated[Path, typer.Option("--repository-map", help="Repository-map JSON.")],
    provider_plan: Annotated[
        Path,
        typer.Option("--provider-plan", help="Stub provider JSON plan with structured tool calls."),
    ],
    allowed_file: Annotated[
        list[str],
        typer.Option("--allowed-file", help="Repository-relative file the agent may edit."),
    ],
    validation_command: Annotated[
        list[str] | None,
        typer.Option(
            "--validation-command",
            help="Configured command name the agent may run for validation.",
        ),
    ] = None,
    max_iterations: Annotated[
        int,
        typer.Option("--max-iterations", min=1, help="Maximum implementation iterations."),
    ] = 1,
) -> None:
    """Run one bounded implementation agent with a deterministic stub provider."""
    try:
        loaded = load_config(config)
        run_store = RunStore(loaded.run_root)
        run_store.create()
        report = run_bounded_implementation(
            config=loaded,
            run_store=run_store,
            provider_plan=provider_plan,
            task_contract_path=task_contract,
            repository_map_path=repository_map,
            allowed_files=allowed_file,
            allowed_validation_commands=validation_command or [],
            max_iterations=max_iterations,
        )
        output = run_store.run_dir / "implementation" / "report.json"
        write_implementation_report(report, output)
    except (ImplementationError, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_implementation_summary(report, output, run_store.run_id)
    if report.status == "failed":
        raise typer.Exit(1)


@app.command("review-task")
def review_task(
    task_contract: Annotated[Path, typer.Option("--task-contract", help="Task-contract JSON.")],
    repository_map: Annotated[Path, typer.Option("--repository-map", help="Repository-map JSON.")],
    implementation_report: Annotated[
        Path,
        typer.Option("--implementation-report", help="Implementation report JSON."),
    ],
    output: Annotated[Path, typer.Option("--output", help="Path for review-report JSON.")],
    provider_findings: Annotated[
        Path | None,
        typer.Option(
            "--provider-findings",
            help="Optional provider-backed semantic findings JSON; findings must cite evidence.",
        ),
    ] = None,
    triage_report: Annotated[
        Path | None,
        typer.Option("--triage-report", help="Optional waveform/assertion triage report JSON."),
    ] = None,
    fail_on_unacceptable: Annotated[
        bool,
        typer.Option("--fail-on-unacceptable/--no-fail-on-unacceptable"),
    ] = False,
) -> None:
    """Review implementation artifacts without editing files or executing commands."""
    try:
        report = review_implementation(
            task_contract_path=task_contract,
            repository_map_path=repository_map,
            implementation_report_path=implementation_report,
            triage_report_path=triage_report,
            provider_findings_path=provider_findings,
        )
        write_review_report(report, output)
    except ReviewError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_review_summary(report, output)
    if fail_on_unacceptable and report.outcome == "unacceptable":
        raise typer.Exit(1)


@app.command("triage-command")
def triage_command(
    command_result: Annotated[
        Path,
        typer.Option("--command-result", help="Command result JSON from run artifacts."),
    ],
    output: Annotated[Path, typer.Option("--output", help="Path for triage-report JSON.")],
) -> None:
    """Extract bounded assertion, simulator, and waveform triage from command artifacts."""
    try:
        report = triage_command_result(command_result)
        write_triage_report(report, output)
    except TriageError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_triage_summary(report, output)


@app.command("assess-verification")
def assess_verification(
    task_contract: Annotated[Path, typer.Option("--task-contract", help="Task-contract JSON.")],
    repository_map: Annotated[Path, typer.Option("--repository-map", help="Repository-map JSON.")],
    implementation_report: Annotated[
        Path,
        typer.Option("--implementation-report", help="Implementation report JSON."),
    ],
    output: Annotated[
        Path,
        typer.Option("--output", help="Path for verification-strength report JSON."),
    ],
    review_report: Annotated[
        Path | None,
        typer.Option("--review-report", help="Optional review-report JSON."),
    ] = None,
    triage_report: Annotated[
        list[Path] | None,
        typer.Option("--triage-report", help="Optional triage-report JSON; may be repeated."),
    ] = None,
    fail_on_insufficient: Annotated[
        bool,
        typer.Option("--fail-on-insufficient/--no-fail-on-insufficient"),
    ] = False,
) -> None:
    """Assess verification strength from existing artifacts without executing commands."""
    try:
        report = assess_verification_strength(
            task_contract_path=task_contract,
            repository_map_path=repository_map,
            implementation_report_path=implementation_report,
            review_report_path=review_report,
            triage_report_paths=triage_report or [],
        )
        write_verification_strength_report(report, output)
    except VerificationStrengthError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_verification_strength_summary(report, output)
    if fail_on_insufficient and report.strength == "insufficient":
        raise typer.Exit(1)


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


def _print_task_contract_summary(contract: object, output: Path) -> None:
    from rtl_agent.task_contract import TaskContract

    assert isinstance(contract, TaskContract)
    _print_json(
        {
            "schema_version": contract.schema_version,
            "issue_path": str(contract.issue_path),
            "output": str(output),
            "requested_behavior": len(contract.requested_behavior),
            "acceptance_criteria": len(contract.acceptance_criteria),
            "validation_commands": len(contract.validation_commands),
            "warnings": len(contract.warnings),
            "repository_map": str(contract.repository_map.path)
            if contract.repository_map is not None
            else None,
        }
    )


def _print_implementation_summary(report: object, output: Path, run_id: str) -> None:
    from rtl_agent.implementation_models import ImplementationReport

    assert isinstance(report, ImplementationReport)
    _print_json(
        {
            "schema_version": report.schema_version,
            "run_id": run_id,
            "status": report.status,
            "output": str(output),
            "provider": report.provider,
            "iterations": report.iterations,
            "applied_files": report.applied_files,
            "validation_results": [
                {
                    "command_name": item.command_name,
                    "status": item.status,
                    "classification": item.classification.category,
                }
                for item in report.validation_results
            ],
            "retry_decisions": [item.model_dump(mode="json") for item in report.retry_decisions],
            "diff_path": str(report.diff_path) if report.diff_path else None,
            "failure_reason": report.failure_reason,
            "warnings": report.warnings,
        }
    )


def _print_review_summary(report: object, output: Path) -> None:
    from rtl_agent.review_models import ReviewFindingSeverity, ReviewReport

    assert isinstance(report, ReviewReport)
    findings = report.deterministic_findings + report.provider_findings
    _print_json(
        {
            "schema_version": report.schema_version,
            "outcome": report.outcome,
            "output": str(output),
            "deterministic_findings": len(report.deterministic_findings),
            "provider_findings": len(report.provider_findings),
            "error_findings": sum(
                finding.severity == ReviewFindingSeverity.ERROR for finding in findings
            ),
            "summary": report.summary,
        }
    )


def _print_triage_summary(report: object, output: Path) -> None:
    from rtl_agent.triage_models import TriageReport

    assert isinstance(report, TriageReport)
    _print_json(
        {
            "schema_version": report.schema_version,
            "command_name": report.command_name,
            "command_status": report.command_status,
            "output": str(output),
            "assertion_failures": len(report.assertion_failures),
            "waveform_references": len(report.waveform_references),
            "simulator_context": len(report.simulator_context),
            "warnings": len(report.warnings),
        }
    )


def _print_verification_strength_summary(report: object, output: Path) -> None:
    from rtl_agent.verification_strength_models import VerificationStrengthReport

    assert isinstance(report, VerificationStrengthReport)
    _print_json(
        {
            "schema_version": report.schema_version,
            "strength": report.strength,
            "score": report.score,
            "output": str(output),
            "signals": len(report.signals),
            "weak_patterns": len(report.weak_patterns),
            "validation_commands": report.validation_commands,
            "summary": report.summary,
        }
    )


def main() -> None:
    app()
