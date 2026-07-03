from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from rtl_agent.artifacts import RunStore
from rtl_agent.assertion_link import (
    AssertionLinkError,
    link_assertion_to_waveform,
    write_link_report,
)
from rtl_agent.benchmark import (
    BenchmarkError,
    report_summary_payload,
    run_benchmark_manifest,
)
from rtl_agent.config import load_config
from rtl_agent.discovery import DiscoveryError, discover_repository, write_repository_map
from rtl_agent.evidence_bundle import (
    EvidenceBundleError,
    export_evidence_bundle,
)
from rtl_agent.evidence_bundle import (
    report_summary_payload as evidence_bundle_summary_payload,
)
from rtl_agent.execution import CommandRunner
from rtl_agent.implementation import (
    ImplementationError,
    run_bounded_implementation,
    write_implementation_report,
)
from rtl_agent.issues import IssueParsingError, parse_issue_file, write_task_contract
from rtl_agent.review import ReviewError, review_implementation, write_review_report
from rtl_agent.signal_reduction import (
    SignalReductionError,
    reduce_relevant_signals,
    write_reduction_report,
)
from rtl_agent.signal_source_map import (
    SignalSourceMapError,
    map_signals_to_source,
    write_signal_source_map,
)
from rtl_agent.triage import TriageError, triage_command_result, write_triage_report
from rtl_agent.verification_strength_service import (
    VerificationStrengthError,
    assess_verification_strength,
    write_verification_strength_report,
)
from rtl_agent.waveform import (
    WaveformSliceError,
    extract_waveform_window,
    write_waveform_slice,
)
from rtl_agent.waveform_comparison import (
    WaveformComparisonError,
    compare_waveforms,
    write_comparison_report,
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


@app.command("extract-waveform-window")
def extract_waveform_window_command(
    output: Annotated[Path, typer.Option("--output", help="Path for waveform-slice JSON.")],
    failure_time: Annotated[
        int,
        typer.Option("--failure-time", help="Failure timestamp in VCD time units."),
    ],
    vcd: Annotated[
        Path | None,
        typer.Option("--vcd", help="Textual VCD waveform path."),
    ] = None,
    before: Annotated[
        int,
        typer.Option("--before", min=0, help="Time units to include before the failure."),
    ] = 0,
    after: Annotated[
        int,
        typer.Option("--after", min=0, help="Time units to include after the failure."),
    ] = 0,
    signal: Annotated[
        list[str] | None,
        typer.Option("--signal", help="Exact hierarchical signal name; may be repeated."),
    ] = None,
    signal_prefix: Annotated[
        list[str] | None,
        typer.Option("--signal-prefix", help="Hierarchical signal-name prefix; may be repeated."),
    ] = None,
    triage_report: Annotated[
        Path | None,
        typer.Option(
            "--triage-report",
            help="Optional triage report used to locate a VCD when --vcd is omitted.",
        ),
    ] = None,
) -> None:
    """Extract a bounded VCD failure window into a waveform-slice artifact."""
    try:
        source = _resolve_waveform_source(vcd, triage_report)
        if output.resolve() == source.resolve():
            raise WaveformSliceError("output path would overwrite the source waveform")
        report = extract_waveform_window(
            vcd_path=source,
            failure_time=failure_time,
            before=before,
            after=after,
            signal_names=signal or [],
            signal_prefixes=signal_prefix or [],
        )
        write_waveform_slice(report, output)
    except WaveformSliceError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_waveform_slice_summary(report, output)


@app.command("link-assertion-waveform")
def link_assertion_waveform_command(
    triage_report: Annotated[
        Path,
        typer.Option("--triage-report", help="Existing triage-report JSON."),
    ],
    output: Annotated[Path, typer.Option("--output", help="Path for the linkage-report JSON.")],
    slice_output: Annotated[
        Path,
        typer.Option("--slice-output", help="Path for the generated waveform-slice JSON."),
    ],
    assertion_index: Annotated[
        int | None,
        typer.Option("--assertion-index", help="Zero-based index of the assertion finding."),
    ] = None,
    assertion_id: Annotated[
        str | None,
        typer.Option("--assertion-id", help="Stable assertion id, e.g. 'assertion-0'."),
    ] = None,
    before: Annotated[
        int,
        typer.Option("--before", min=0, help="Time units to include before the failure."),
    ] = 0,
    after: Annotated[
        int,
        typer.Option("--after", min=0, help="Time units to include after the failure."),
    ] = 0,
    signal: Annotated[
        list[str] | None,
        typer.Option("--signal", help="Exact hierarchical signal name; may be repeated."),
    ] = None,
    signal_prefix: Annotated[
        list[str] | None,
        typer.Option("--signal-prefix", help="Hierarchical signal-name prefix; may be repeated."),
    ] = None,
    waveform_path: Annotated[
        Path | None,
        typer.Option(
            "--waveform-path",
            help="Disambiguate which referenced VCD to use when triage lists several.",
        ),
    ] = None,
) -> None:
    """Link a triaged assertion failure to a bounded VCD waveform slice."""
    try:
        report = link_assertion_to_waveform(
            triage_report,
            slice_output,
            assertion_index=assertion_index,
            assertion_id=assertion_id,
            before=before,
            after=after,
            signal_names=signal or [],
            signal_prefixes=signal_prefix or [],
            waveform_path=waveform_path,
        )
        write_link_report(report, output)
    except AssertionLinkError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_assertion_link_summary(report, output)


@app.command("reduce-signals")
def reduce_signals_command(
    waveform_slice: Annotated[
        Path,
        typer.Option("--waveform-slice", help="Existing waveform-slice JSON to reduce."),
    ],
    output: Annotated[Path, typer.Option("--output", help="Path for the reduction-report JSON.")],
    reduced_slice_output: Annotated[
        Path,
        typer.Option("--reduced-slice-output", help="Path for the reduced waveform-slice JSON."),
    ],
    assertion_link: Annotated[
        Path | None,
        typer.Option("--assertion-link", help="Optional assertion-link report for context."),
    ] = None,
    assertion_signal: Annotated[
        str | None,
        typer.Option("--assertion-signal", help="Assertion signal name or leaf for ranking."),
    ] = None,
    assertion_summary: Annotated[
        str | None,
        typer.Option("--assertion-summary", help="Assertion summary text for token matching."),
    ] = None,
    max_signals: Annotated[
        int,
        typer.Option("--max-signals", min=1, help="Maximum retained signals."),
    ] = 32,
) -> None:
    """Reduce a waveform slice to a bounded, evidence-ranked relevant signal set."""
    try:
        report = reduce_relevant_signals(
            waveform_slice,
            reduced_slice_output,
            assertion_link_path=assertion_link,
            assertion_signal=assertion_signal,
            assertion_summary=assertion_summary,
            max_signals=max_signals,
        )
        write_reduction_report(report, output)
    except SignalReductionError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_reduction_summary(report, output)


@app.command("compare-waveforms")
def compare_waveforms_command(
    failing_slice: Annotated[
        Path,
        typer.Option("--failing-slice", help="Failing waveform-slice JSON."),
    ],
    passing_slice: Annotated[
        Path,
        typer.Option("--passing-slice", help="Passing/reference waveform-slice JSON."),
    ],
    output: Annotated[Path, typer.Option("--output", help="Path for the comparison-report JSON.")],
    max_signals: Annotated[
        int,
        typer.Option("--max-signals", min=1, help="Maximum diverging signals reported."),
    ] = 256,
) -> None:
    """Compare a failing waveform slice against a passing reference slice."""
    try:
        report = compare_waveforms(failing_slice, passing_slice, max_signals=max_signals)
        write_comparison_report(report, output)
    except WaveformComparisonError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_comparison_summary(report, output)


@app.command("map-signals")
def map_signals_command(
    repository_map: Annotated[Path, typer.Option("--repository-map", help="Repository-map JSON.")],
    output: Annotated[Path, typer.Option("--output", help="Path for the mapping-report JSON.")],
    signal: Annotated[
        list[str] | None,
        typer.Option("--signal", help="Hierarchical signal name to map; may be repeated."),
    ] = None,
    waveform_slice: Annotated[
        Path | None,
        typer.Option("--waveform-slice", help="Waveform slice to read signal names from."),
    ] = None,
    comparison: Annotated[
        Path | None,
        typer.Option("--comparison", help="Comparison report to read signal names from."),
    ] = None,
    max_signals: Annotated[
        int,
        typer.Option("--max-signals", min=1, help="Maximum signals mapped."),
    ] = 1024,
) -> None:
    """Map hierarchical waveform signals to candidate RTL declaration sources."""
    try:
        report = map_signals_to_source(
            repository_map,
            signal_names=signal or [],
            waveform_slice_path=waveform_slice,
            comparison_path=comparison,
            max_signals=max_signals,
        )
        write_signal_source_map(report, output)
    except SignalSourceMapError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_signal_source_map_summary(report, output)


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


@app.command("run-benchmark")
def run_benchmark(
    manifest: Annotated[
        Path,
        typer.Option("--manifest", help="Benchmark manifest YAML."),
    ],
    fail_on_unmet_expected: Annotated[
        bool,
        typer.Option("--fail-on-unmet-expected/--no-fail-on-unmet-expected"),
    ] = False,
) -> None:
    """Run a local deterministic benchmark manifest using existing command artifacts."""
    try:
        report = run_benchmark_manifest(manifest)
    except BenchmarkError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_json(report_summary_payload(report))
    if fail_on_unmet_expected and report.status != "passed":
        raise typer.Exit(1)


@app.command("export-evidence")
def export_evidence(
    run_dir: Annotated[
        Path,
        typer.Option("--run-dir", help="Existing rtl-agent run artifact directory."),
    ],
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Directory for compact evidence bundle index."),
    ],
    fail_on_failed_export: Annotated[
        bool,
        typer.Option("--fail-on-failed-export/--no-fail-on-failed-export"),
    ] = False,
) -> None:
    """Export a compact local evidence-bundle index from existing run artifacts."""
    try:
        report = export_evidence_bundle(run_dir=run_dir, output_dir=output_dir)
    except EvidenceBundleError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_json(evidence_bundle_summary_payload(report))
    if fail_on_failed_export and report.status == "failed":
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


def _resolve_waveform_source(vcd: Path | None, triage_report: Path | None) -> Path:
    if vcd is not None:
        return vcd
    if triage_report is None:
        raise WaveformSliceError("either --vcd or --triage-report must be provided")

    from pydantic import ValidationError

    from rtl_agent.triage_models import TriageReport

    try:
        report = TriageReport.model_validate_json(triage_report.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise WaveformSliceError(f"could not load triage report: {triage_report}") from exc
    for reference in report.waveform_references:
        if reference.exists and reference.resolved_path and reference.path.endswith(".vcd"):
            return reference.resolved_path
    raise WaveformSliceError("no existing .vcd waveform reference found in triage report")


def _print_waveform_slice_summary(report: object, output: Path) -> None:
    from rtl_agent.waveform_slice_models import WaveformSliceReport

    assert isinstance(report, WaveformSliceReport)
    _print_json(
        {
            "schema_version": report.schema_version,
            "output": str(output),
            "source": str(report.source.path),
            "timescale": report.source.timescale,
            "requested_start": report.window.requested_start,
            "requested_end": report.window.requested_end,
            "observed_start": report.window.observed_start,
            "observed_end": report.window.observed_end,
            "selected_signals": len(report.selected_signals),
            "value_changes": len(report.value_changes),
            "warnings": len(report.warnings),
        }
    )


def _print_signal_source_map_summary(report: object, output: Path) -> None:
    from rtl_agent.signal_source_map_models import SignalSourceMapReport

    assert isinstance(report, SignalSourceMapReport)
    _print_json(
        {
            "schema_version": report.schema_version,
            "output": str(output),
            "total_signals": report.total_signals,
            "exact": report.exact_count,
            "probable": report.probable_count,
            "ambiguous": report.ambiguous_count,
            "unresolved": report.unresolved_count,
            "warnings": len(report.warnings),
        }
    )


def _print_comparison_summary(report: object, output: Path) -> None:
    from rtl_agent.waveform_comparison_models import WaveformComparisonReport

    assert isinstance(report, WaveformComparisonReport)
    _print_json(
        {
            "schema_version": report.schema_version,
            "output": str(output),
            "time_basis": report.time_basis.kind,
            "normalized": report.time_basis.normalized,
            "common_start": report.time_basis.common_start,
            "common_end": report.time_basis.common_end,
            "shared_signals": report.shared_signal_count,
            "added_signals": len(report.added_signals),
            "removed_signals": len(report.removed_signals),
            "diverging_signals": len(report.diverging_signals),
            "identical_signals": len(report.identical_signals),
            "global_earliest_divergence_time": report.global_earliest_divergence_time,
            "warnings": len(report.warnings),
        }
    )


def _print_reduction_summary(report: object, output: Path) -> None:
    from rtl_agent.relevant_signal_models import RelevantSignalReductionReport

    assert isinstance(report, RelevantSignalReductionReport)
    _print_json(
        {
            "schema_version": report.schema_version,
            "output": str(output),
            "reduced_slice_path": str(report.reduced_slice_path),
            "failure_time": report.failure_time,
            "total_candidate_signals": report.total_candidate_signals,
            "retained_signals": len(report.retained_signals),
            "top_signals": [signal.name for signal in report.retained_signals[:5]],
            "warnings": len(report.warnings),
        }
    )


def _print_assertion_link_summary(report: object, output: Path) -> None:
    from rtl_agent.assertion_waveform_link_models import AssertionWaveformLinkReport

    assert isinstance(report, AssertionWaveformLinkReport)
    _print_json(
        {
            "schema_version": report.schema_version,
            "output": str(output),
            "assertion_id": report.selected_assertion.assertion_id,
            "waveform": str(report.selected_waveform.resolved_path),
            "failure_timestamp_ticks": report.timestamp_conversion.failure_timestamp_ticks,
            "timescale": report.timestamp_conversion.vcd_timescale,
            "exact_conversion": report.timestamp_conversion.exact,
            "waveform_slice_path": str(report.waveform_slice_path),
            "value_changes": report.slice_value_change_count,
            "warnings": len(report.warnings),
            "unresolved_ambiguities": len(report.unresolved_ambiguities),
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
