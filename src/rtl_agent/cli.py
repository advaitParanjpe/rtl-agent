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
from rtl_agent.counterfactual import CounterfactualError, run_counterfactual
from rtl_agent.discovery import DiscoveryError, discover_repository, write_repository_map
from rtl_agent.evidence_bundle import (
    EvidenceBundleError,
    export_evidence_bundle,
)
from rtl_agent.evidence_bundle import (
    report_summary_payload as evidence_bundle_summary_payload,
)
from rtl_agent.execution import CommandRunner
from rtl_agent.experiment_matrix import ExperimentMatrixError, run_experiment_matrix
from rtl_agent.failure_divergence_graph import (
    FailureDivergenceGraphError,
    build_failure_divergence_graph,
    write_divergence_graph,
)
from rtl_agent.failure_family import (
    FailureFamilyError,
    cluster_fingerprints,
    render_cluster_markdown,
    write_cluster_report,
)
from rtl_agent.failure_fingerprint import (
    FailureFingerprintError,
    compare_fingerprints,
    fingerprint_run,
    write_fingerprint_comparison,
    write_fingerprint_report,
)
from rtl_agent.failure_intelligence_run import (
    FailureIntelligenceRunError,
    run_failure_intelligence,
)
from rtl_agent.failure_package import FailurePackageError, export_failure_package
from rtl_agent.failure_report import (
    FailureReportError,
    synthesize_failure_report,
    write_failure_markdown,
    write_failure_report,
)
from rtl_agent.implementation import (
    ImplementationError,
    run_bounded_implementation,
    write_implementation_report,
)
from rtl_agent.intervention_templates import (
    InterventionTemplateError,
    generate_interventions,
)
from rtl_agent.issues import IssueParsingError, parse_issue_file, write_task_contract
from rtl_agent.mvp_demo import MvpDemoError, run_mvp_demo
from rtl_agent.reduction import StimulusReductionError, minimize_stimulus
from rtl_agent.review import ReviewError, review_implementation, write_review_report
from rtl_agent.rtl_driver_trace import (
    RtlDriverTraceError,
    trace_drivers,
    write_driver_trace,
)
from rtl_agent.run_inspection import (
    RunInspectionError,
    inspect_run,
    write_inspection_report,
)
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


@app.command("trace-drivers")
def trace_drivers_command(
    signal_source_map: Annotated[
        Path,
        typer.Option("--signal-source-map", help="Signal-source-map report JSON."),
    ],
    repository_map: Annotated[Path, typer.Option("--repository-map", help="Repository-map JSON.")],
    output: Annotated[Path, typer.Option("--output", help="Path for the driver-trace JSON.")],
    max_depth: Annotated[
        int,
        typer.Option("--max-depth", min=0, help="Upstream dependency expansion depth."),
    ] = 2,
    max_nodes: Annotated[
        int,
        typer.Option("--max-nodes", min=1, help="Maximum dependency nodes visited."),
    ] = 64,
) -> None:
    """Extract bounded textual driver and dependency evidence for mapped signals."""
    try:
        report = trace_drivers(
            signal_source_map,
            repository_map,
            max_depth=max_depth,
            max_nodes=max_nodes,
        )
        write_driver_trace(report, output)
    except RtlDriverTraceError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_driver_trace_summary(report, output)


@app.command("divergence-graph")
def divergence_graph_command(
    comparison: Annotated[
        Path,
        typer.Option("--comparison", help="Waveform-comparison report JSON."),
    ],
    signal_source_map: Annotated[
        Path,
        typer.Option("--signal-source-map", help="Signal-source-map report JSON."),
    ],
    driver_trace: Annotated[
        Path,
        typer.Option("--driver-trace", help="Driver-trace report JSON."),
    ],
    output: Annotated[Path, typer.Option("--output", help="Path for the divergence-graph JSON.")],
    max_depth: Annotated[
        int,
        typer.Option("--max-depth", min=0, help="Graph depth from divergence roots."),
    ] = 3,
    max_nodes: Annotated[
        int,
        typer.Option("--max-nodes", min=1, help="Maximum graph nodes."),
    ] = 128,
) -> None:
    """Compose comparison divergences and driver evidence into a failure divergence graph."""
    try:
        report = build_failure_divergence_graph(
            comparison,
            signal_source_map,
            driver_trace,
            max_depth=max_depth,
            max_nodes=max_nodes,
        )
        write_divergence_graph(report, output)
    except FailureDivergenceGraphError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_divergence_graph_summary(report, output)


@app.command("synthesize-failure-report")
def synthesize_failure_report_command(
    divergence_graph: Annotated[
        Path,
        typer.Option("--divergence-graph", help="Failure-divergence-graph report JSON."),
    ],
    output: Annotated[Path, typer.Option("--output", help="Path for the failure-report JSON.")],
    markdown_output: Annotated[
        Path | None,
        typer.Option(
            "--markdown-output",
            help="Path for the Markdown summary (default: output with a .md suffix).",
        ),
    ] = None,
    reduction: Annotated[
        Path | None,
        typer.Option("--reduction", help="Optional relevant-signal reduction report JSON."),
    ] = None,
    driver_trace: Annotated[
        Path | None,
        typer.Option("--driver-trace", help="Optional driver-trace report JSON."),
    ] = None,
    verification_strength: Annotated[
        Path | None,
        typer.Option("--verification-strength", help="Optional verification-strength report JSON."),
    ] = None,
    review: Annotated[
        Path | None,
        typer.Option("--review", help="Optional review report JSON."),
    ] = None,
) -> None:
    """Synthesize a compact, evidence-cited failure report (JSON + Markdown)."""
    try:
        report = synthesize_failure_report(
            divergence_graph,
            reduction_path=reduction,
            driver_trace_path=driver_trace,
            verification_strength_path=verification_strength,
            review_path=review,
        )
        write_failure_report(report, output)
        markdown_path = markdown_output or output.with_suffix(".md")
        write_failure_markdown(report, markdown_path)
    except FailureReportError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_failure_report_summary(report, output, markdown_path)


@app.command("run-failure-intelligence")
def run_failure_intelligence_command(
    failing_vcd: Annotated[Path, typer.Option("--failing-vcd", help="Failing VCD waveform.")],
    passing_vcd: Annotated[
        Path,
        typer.Option("--passing-vcd", help="Passing/reference VCD waveform."),
    ],
    repo: Annotated[Path, typer.Option("--repo", help="RTL repository root to discover.")],
    failure_time: Annotated[
        int,
        typer.Option("--failure-time", help="Failure timestamp in VCD time units."),
    ],
    run_root: Annotated[
        Path,
        typer.Option("--run-root", help="Directory holding run artifact directories."),
    ] = Path(".rtl-agent/runs"),
    before: Annotated[
        int,
        typer.Option("--before", min=0, help="Time units to include before the failure."),
    ] = 0,
    after: Annotated[
        int,
        typer.Option("--after", min=0, help="Time units to include after the failure."),
    ] = 0,
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Optional rtl-agent YAML config for discovery limits."),
    ] = None,
    run_id: Annotated[
        str | None,
        typer.Option("--run-id", help="Explicit run identifier (default: generated)."),
    ] = None,
    verification_strength: Annotated[
        Path | None,
        typer.Option("--verification-strength", help="Optional verification-strength report JSON."),
    ] = None,
    review: Annotated[
        Path | None,
        typer.Option("--review", help="Optional review report JSON."),
    ] = None,
    resume: Annotated[
        bool,
        typer.Option("--resume/--no-resume", help="Reuse valid existing stage artifacts."),
    ] = False,
    replay_from: Annotated[
        str | None,
        typer.Option("--replay-from", help="Regenerate from this stage onward."),
    ] = None,
) -> None:
    """Orchestrate the failure-intelligence stages into one run directory."""
    try:
        loaded = load_config(config) if config else None
        discovery_config = loaded.discovery if loaded else None
        run_store = RunStore(run_root, run_id=run_id)
        # Resume/replay operate on an existing run directory; only create a fresh one otherwise.
        if not ((resume or replay_from is not None) and run_store.run_dir.exists()):
            run_store.create()
        manifest = run_failure_intelligence(
            run_store,
            failing_vcd=failing_vcd,
            passing_vcd=passing_vcd,
            repository_root=repo,
            failure_time=failure_time,
            before=before,
            after=after,
            discovery_config=discovery_config,
            verification_strength_path=verification_strength,
            review_path=review,
            resume=resume,
            replay_from=replay_from,
        )
    except (FailureIntelligenceRunError, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_run_manifest_summary(manifest)
    if manifest.status == "failed":
        raise typer.Exit(1)


@app.command("inspect-run")
def inspect_run_command(
    run_dir: Annotated[
        Path,
        typer.Option("--run-dir", help="Existing failure-intelligence run directory."),
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Optional path for the JSON inspection report."),
    ] = None,
) -> None:
    """Validate an existing run directory against its manifest (read-only)."""
    try:
        report = inspect_run(run_dir)
        if output is not None:
            write_inspection_report(report, output)
    except RunInspectionError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_inspection_summary(report, output)
    if not report.valid:
        raise typer.Exit(1)


@app.command("fingerprint-run")
def fingerprint_run_command(
    run_dir: Annotated[
        Path,
        typer.Option("--run-dir", help="Existing failure-intelligence run directory."),
    ],
    output: Annotated[
        Path,
        typer.Option("--output", help="Path for the failure-fingerprint JSON."),
    ],
) -> None:
    """Build a stable read-only failure fingerprint from existing run artifacts."""
    try:
        report = fingerprint_run(run_dir)
        write_fingerprint_report(report, output)
    except FailureFingerprintError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_fingerprint_summary(report, output)


@app.command("compare-fingerprints")
def compare_fingerprints_command(
    left: Annotated[Path, typer.Option("--left", help="Left failure-fingerprint JSON.")],
    right: Annotated[Path, typer.Option("--right", help="Right failure-fingerprint JSON.")],
    output: Annotated[
        Path,
        typer.Option("--output", help="Path for the fingerprint-comparison JSON."),
    ],
) -> None:
    """Compare two stable failure fingerprints without re-running analysis."""
    try:
        report = compare_fingerprints(left, right)
        write_fingerprint_comparison(report, output)
    except FailureFingerprintError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_fingerprint_comparison_summary(report, output)


@app.command("cluster-failures")
def cluster_failures_command(
    output: Annotated[
        Path,
        typer.Option("--output", help="Directory or path prefix for the regression report."),
    ],
    fingerprint: Annotated[
        list[Path] | None,
        typer.Option("--fingerprint", help="Failure-fingerprint JSON file; may be repeated."),
    ] = None,
    fingerprint_dir: Annotated[
        Path | None,
        typer.Option("--fingerprint-dir", help="Directory of failure-fingerprint JSON files."),
    ] = None,
    strict: Annotated[
        bool,
        typer.Option(
            "--strict/--permissive",
            help="Fail on any invalid input (strict) or exclude and warn (permissive).",
        ),
    ] = False,
) -> None:
    """Group existing failure fingerprints into observed failure families (read-only)."""
    try:
        report = cluster_fingerprints(
            fingerprint_paths=list(fingerprint or []),
            fingerprint_dir=fingerprint_dir,
            strict=strict,
        )
        json_path, markdown_path = _cluster_output_paths(output)
        write_cluster_report(report, json_path)
        render_cluster_markdown(report, markdown_path)
    except FailureFamilyError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_cluster_summary(report, json_path, markdown_path)


@app.command("minimize-stimulus")
def minimize_stimulus_command(
    baseline_run: Annotated[
        Path, typer.Option("--baseline-run", help="Validated failure-intelligence run dir.")
    ],
    repo: Annotated[Path, typer.Option("--repo", help="Target Git RTL repository root.")],
    config: Annotated[Path, typer.Option("--config", "-c", help="rtl-agent YAML config.")],
    command: Annotated[str, typer.Option("--command", help="Named configured simulator command.")],
    stimulus: Annotated[Path, typer.Option("--stimulus", help="Structured failing stimulus JSON.")],
    output: Annotated[Path, typer.Option("--output", help="Experiment output directory.")],
    max_evaluations: Annotated[
        int, typer.Option("--max-evaluations", min=1, help="Maximum candidate evaluations.")
    ] = 32,
    timeout: Annotated[
        int | None, typer.Option("--timeout", min=1, help="Timeout (s) per evaluation.")
    ] = None,
    baseline_commit: Annotated[
        str | None,
        typer.Option("--baseline-commit", help="Commit/ref for the worktree (default HEAD)."),
    ] = None,
) -> None:
    """Minimize a structured failing stimulus while preserving the failure family."""
    try:
        report = minimize_stimulus(
            baseline_run=baseline_run,
            repo=repo,
            config_path=config,
            command=command,
            stimulus_path=stimulus,
            output=output,
            max_evaluations=max_evaluations,
            timeout=timeout,
            baseline_commit=baseline_commit,
        )
    except StimulusReductionError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_minimize_summary(report, output)


@app.command("run-experiment-matrix")
def run_experiment_matrix_command(
    baseline_run: Annotated[
        Path, typer.Option("--baseline-run", help="Validated failure-intelligence run dir.")
    ],
    reduction_report: Annotated[
        Path, typer.Option("--reduction-report", help="Stimulus reduction report JSON.")
    ],
    repo: Annotated[Path, typer.Option("--repo", help="Target Git RTL repository root.")],
    config: Annotated[Path, typer.Option("--config", "-c", help="rtl-agent YAML config.")],
    command: Annotated[str, typer.Option("--command", help="Named configured simulator command.")],
    interventions: Annotated[
        Path, typer.Option("--interventions", help="Intervention manifest JSON.")
    ],
    output: Annotated[Path, typer.Option("--output", help="Experiment matrix output directory.")],
    max_experiments: Annotated[
        int, typer.Option("--max-experiments", min=1, help="Maximum executed experiments.")
    ] = 12,
    timeout: Annotated[
        int | None, typer.Option("--timeout", min=1, help="Timeout (s) per experiment.")
    ] = None,
    baseline_commit: Annotated[
        str | None,
        typer.Option("--baseline-commit", help="Commit/ref for the worktrees (default HEAD)."),
    ] = None,
) -> None:
    """Run a bounded set of manual interventions against one minimized counterexample."""
    try:
        report = run_experiment_matrix(
            baseline_run=baseline_run,
            reduction_report=reduction_report,
            repo=repo,
            config_path=config,
            command=command,
            interventions=interventions,
            output=output,
            max_experiments=max_experiments,
            timeout=timeout,
            baseline_commit=baseline_commit,
        )
    except ExperimentMatrixError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_experiment_matrix_summary(report, output)


@app.command("generate-interventions")
def generate_interventions_command(
    failure_run: Annotated[
        Path, typer.Option("--failure-run", help="Validated failure-intelligence run dir.")
    ],
    repo: Annotated[Path, typer.Option("--repo", help="Target Git RTL repository root.")],
    allowed_file: Annotated[
        list[str],
        typer.Option("--allowed-file", help="Allowed source file (repeatable)."),
    ],
    output: Annotated[Path, typer.Option("--output", help="Generation output directory.")],
    max_candidates: Annotated[
        int, typer.Option("--max-candidates", min=1, help="Maximum candidate count.")
    ] = 8,
    reduction_report: Annotated[
        Path | None,
        typer.Option("--reduction-report", help="Optional minimized-stimulus reduction report."),
    ] = None,
    baseline_commit: Annotated[
        str | None,
        typer.Option("--baseline-commit", help="Commit/ref to validate edits against (HEAD)."),
    ] = None,
) -> None:
    """Generate reviewable intervention candidates from failure evidence (generation only)."""
    try:
        report = generate_interventions(
            failure_run=failure_run,
            repo=repo,
            allowed_files=allowed_file,
            output=output,
            max_candidates=max_candidates,
            reduction_report=reduction_report,
            baseline_commit=baseline_commit,
        )
    except InterventionTemplateError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_generate_interventions_summary(report, output)


@app.command("run-mvp-demo")
def run_mvp_demo_command(
    failure_run: Annotated[
        Path, typer.Option("--failure-run", help="Validated failure-intelligence run dir.")
    ],
    repo: Annotated[Path, typer.Option("--repo", help="Target Git RTL repository root.")],
    config: Annotated[Path, typer.Option("--config", "-c", help="rtl-agent YAML config.")],
    command: Annotated[str, typer.Option("--command", help="Named configured simulator command.")],
    stimulus: Annotated[Path, typer.Option("--stimulus", help="Structured failing stimulus JSON.")],
    allowed_file: Annotated[
        list[str],
        typer.Option("--allowed-file", help="Allowed source file for generation (repeatable)."),
    ],
    output: Annotated[Path, typer.Option("--output", help="Demonstration output directory.")],
    max_candidates: Annotated[
        int, typer.Option("--max-candidates", min=1, help="Maximum intervention candidates.")
    ] = 8,
    max_experiments: Annotated[
        int, typer.Option("--max-experiments", min=1, help="Maximum experiments to run.")
    ] = 12,
    timeout: Annotated[
        int | None, typer.Option("--timeout", min=1, help="Timeout (s) per simulation.")
    ] = None,
    baseline_commit: Annotated[
        str | None,
        typer.Option("--baseline-commit", help="Commit/ref for the worktrees (default HEAD)."),
    ] = None,
) -> None:
    """Run the full evidence-guided counterfactual demonstration (composition only)."""
    try:
        summary = run_mvp_demo(
            failure_run=failure_run,
            repo=repo,
            config_path=config,
            command=command,
            stimulus=stimulus,
            allowed_files=allowed_file,
            output=output,
            max_candidates=max_candidates,
            max_experiments=max_experiments,
            timeout=timeout,
            baseline_commit=baseline_commit,
        )
    except MvpDemoError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_mvp_demo_summary(summary, output)


@app.command("export-failure-package")
def export_failure_package_command(
    run_dir: Annotated[
        Path,
        typer.Option("--run-dir", help="Existing failure-intelligence run directory."),
    ],
    output: Annotated[
        Path,
        typer.Option("--output", help="Directory to write the portable failure package into."),
    ],
    allow_failed: Annotated[
        bool,
        typer.Option(
            "--allow-failed/--no-allow-failed",
            help="Allow exporting a failed-but-internally-consistent run.",
        ),
    ] = False,
) -> None:
    """Export a validated run directory into a portable failure package (read-only)."""
    try:
        manifest = export_failure_package(run_dir, output, allow_failed=allow_failed)
    except FailurePackageError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_failure_package_summary(manifest, output)


@app.command("run-counterfactual")
def run_counterfactual_command(
    baseline_run: Annotated[
        Path,
        typer.Option("--baseline-run", help="Existing validated failure-intelligence run dir."),
    ],
    repo: Annotated[Path, typer.Option("--repo", help="Target Git RTL repository root.")],
    config: Annotated[Path, typer.Option("--config", "-c", help="rtl-agent YAML config.")],
    command: Annotated[str, typer.Option("--command", help="Named configured command to rerun.")],
    output_run: Annotated[
        Path,
        typer.Option("--output-run", help="Directory to write the experiment into."),
    ],
    allowed_file: Annotated[
        list[str] | None,
        typer.Option("--allowed-file", help="Repository-relative file the intervention may edit."),
    ] = None,
    patch: Annotated[
        Path | None,
        typer.Option("--patch", help="Unified diff to apply as the intervention."),
    ] = None,
    replace_file: Annotated[
        str | None,
        typer.Option("--replace-file", help="Structured replace_text target file."),
    ] = None,
    replace_old: Annotated[
        str | None,
        typer.Option("--replace-old", help="Structured replace_text exact old text."),
    ] = None,
    replace_new: Annotated[
        str | None,
        typer.Option("--replace-new", help="Structured replace_text new text."),
    ] = None,
    baseline_commit: Annotated[
        str | None,
        typer.Option("--baseline-commit", help="Commit/ref for the worktree (default HEAD)."),
    ] = None,
    description: Annotated[
        str | None,
        typer.Option("--description", help="Human-readable intervention description."),
    ] = None,
) -> None:
    """Run one manual counterfactual intervention experiment against a baseline run."""
    try:
        report = run_counterfactual(
            baseline_run=baseline_run,
            repo=repo,
            config_path=config,
            command=command,
            output_run=output_run,
            allowed_files=allowed_file or [],
            patch=patch,
            replace_file=replace_file,
            replace_old=replace_old,
            replace_new=replace_new,
            baseline_commit=baseline_commit,
            description=description,
        )
    except CounterfactualError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    _print_counterfactual_summary(report, output_run)


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


def _print_counterfactual_summary(report: object, output_run: Path) -> None:
    from rtl_agent.counterfactual_models import CounterfactualExperimentReport

    assert isinstance(report, CounterfactualExperimentReport)
    _print_json(
        {
            "schema_version": report.schema_version,
            "experiment_id": report.experiment_id,
            "experiment_dir": str(output_run),
            "outcome": report.outcome,
            "intervention_applied": report.intervention.applied,
            "command_status": report.execution.status if report.execution else None,
            "baseline_failure_time": report.baseline_failure.failure_time,
            "intervention_failure_time": report.intervention_failure.failure_time,
            "observable_differences": len(report.observable_differences),
            "warnings": len(report.warnings),
        }
    )


def _print_failure_package_summary(manifest: object, output: Path) -> None:
    from rtl_agent.failure_package_models import FailurePackageManifest

    assert isinstance(manifest, FailurePackageManifest)
    _print_json(
        {
            "schema_version": manifest.schema_version,
            "package_dir": str(output),
            "package_status": manifest.package_status,
            "run_id": manifest.run_id,
            "verified": manifest.verified,
            "file_count": manifest.file_count,
            "total_bytes": manifest.total_bytes,
            "warnings": len(manifest.warnings),
        }
    )


def _print_inspection_summary(report: object, output: Path | None) -> None:
    from rtl_agent.run_inspection_models import RunInspectionReport

    assert isinstance(report, RunInspectionReport)
    _print_json(
        {
            "schema_version": report.schema_version,
            "run_dir": str(report.run_dir),
            "output": str(output) if output is not None else None,
            "valid": report.valid,
            "manifest_status": report.manifest_status,
            "valid_artifacts": report.valid_artifacts,
            "missing_artifacts": report.missing_artifacts,
            "invalid_artifacts": report.invalid_artifacts,
            "external_inputs_present": report.external_inputs_present,
            "stages": [{"name": stage.name, "validity": stage.validity} for stage in report.stages],
            "warnings": len(report.warnings),
        }
    )


def _cluster_output_paths(output: Path) -> tuple[Path, Path]:
    # A directory (or dir-like path) receives named report files; otherwise the
    # given path is the JSON report and the Markdown sibling gets a .md suffix.
    if output.is_dir() or output.suffix == "":
        return output / "regression-families.json", output / "regression-families.md"
    return output, output.with_suffix(".md")


def _print_minimize_summary(report: object, output: Path) -> None:
    from rtl_agent.reduction_models import StimulusReductionReport

    assert isinstance(report, StimulusReductionReport)
    original = report.original_item_count
    minimized = report.minimized_item_count
    percent = round(100 * (original - minimized) / original) if original else 0
    _print_json(
        {
            "schema_version": report.schema_version,
            "output": str(output),
            "original_item_count": original,
            "minimized_item_count": minimized,
            "percent_reduced": percent,
            "evaluations": report.total_evaluations,
            "cache_hits": report.cache_hits,
            "final_classification": report.final_classification,
            "termination_reason": report.termination_reason,
        }
    )


def _print_mvp_demo_summary(summary: object, output: Path) -> None:
    from rtl_agent.mvp_demo_models import MvpDemoSummary

    assert isinstance(summary, MvpDemoSummary)
    _print_json(
        {
            "schema_version": summary.schema_version,
            "output": str(output),
            "summary_json": str(output / "mvp-demo-summary.json"),
            "summary_markdown": str(output / "mvp-demo-summary.md"),
            "stages": [f"{s.stage}={s.status}" for s in summary.stages],
            "original_failure_family": (summary.original_failure.family_digest or "")[:16],
            "minimized_items": (
                f"{summary.minimization.original_item_count} -> "
                f"{summary.minimization.minimized_item_count}"
            ),
            "candidate_counts": summary.candidate_counts,
            "observed_effect_counts": summary.observed_effect_counts,
            "next_debug_checks": [c.statement for c in summary.next_debug_checks],
        }
    )


def _print_generate_interventions_summary(report: object, output: Path) -> None:
    from rtl_agent.intervention_template_models import InterventionTemplateReport

    assert isinstance(report, InterventionTemplateReport)
    candidates = [
        {
            "candidate_id": c.candidate_id,
            "template_kind": str(c.template_kind),
            "confidence": str(c.confidence),
            "location": f"{c.file}:{c.source_line}",
            "affected_signal": c.affected_signal,
        }
        for c in report.candidates
    ]
    _print_json(
        {
            "schema_version": report.schema_version,
            "output": str(output),
            "manifest": str(output / "interventions.json"),
            "target_commit": report.target_commit,
            "candidates": candidates,
            "summary": report.summary.model_dump(mode="json"),
        }
    )


def _print_experiment_matrix_summary(report: object, output: Path) -> None:
    from rtl_agent.experiment_matrix_models import ExperimentMatrixReport

    assert isinstance(report, ExperimentMatrixReport)
    rows = []
    for row in report.rows:
        delta = None
        if row.result_failure_time is not None and row.baseline_failure_time is not None:
            delta = row.result_failure_time - row.baseline_failure_time
        rows.append(
            {
                "intervention_id": row.intervention_id,
                "execution_status": row.execution_status,
                "counterfactual_outcome": row.counterfactual_outcome,
                "fingerprint_relation": row.fingerprint_relation,
                "result_family_digest": (
                    row.result_family_digest[:12] if row.result_family_digest else None
                ),
                "failure_time_shift": delta,
                "from_cache": row.from_cache,
                "artifact_dir": row.artifact_dir,
            }
        )
    _print_json(
        {
            "schema_version": report.schema_version,
            "output": str(output),
            "matrix": rows,
            "summary": report.summary.model_dump(mode="json"),
        }
    )


def _print_cluster_summary(report: object, json_path: Path, markdown_path: Path) -> None:
    from rtl_agent.failure_family_models import FailureFamilyClusterReport

    assert isinstance(report, FailureFamilyClusterReport)
    summary = report.input_summary
    _print_json(
        {
            "schema_version": report.schema_version,
            "json_report": str(json_path),
            "markdown_report": str(markdown_path),
            "total_inputs": summary.total_inputs,
            "valid_fingerprints": summary.valid_fingerprints,
            "family_count": summary.family_count,
            "exact_duplicates": summary.exact_duplicate_count,
            "outliers": summary.outlier_count,
            "insufficient_evidence": summary.insufficient_evidence_count,
            "excluded_inputs": summary.excluded_invalid,
        }
    )


def _print_fingerprint_summary(report: object, output: Path) -> None:
    from rtl_agent.failure_fingerprint_models import FailureFingerprintReport

    assert isinstance(report, FailureFingerprintReport)
    _print_json(
        {
            "schema_version": report.schema_version,
            "output": str(output),
            "exact_digest": report.exact_digest,
            "family_digest": report.family_digest,
            "earliest_divergent_signals": report.earliest_divergent_signals,
            "assertion_identity": report.assertion_identity,
            "insufficient_evidence": report.insufficient_evidence,
            "warnings": len(report.warnings),
        }
    )


def _print_fingerprint_comparison_summary(report: object, output: Path) -> None:
    from rtl_agent.failure_fingerprint_models import FingerprintComparisonReport

    assert isinstance(report, FingerprintComparisonReport)
    _print_json(
        {
            "schema_version": report.schema_version,
            "output": str(output),
            "match_kind": report.match_kind,
            "exact_match": report.exact_match,
            "family_match": report.family_match,
            "differing_components": [
                item.component for item in report.component_matches if not item.match
            ],
            "summary": report.summary,
            "warnings": len(report.warnings),
        }
    )


def _print_run_manifest_summary(manifest: object) -> None:
    from rtl_agent.failure_intelligence_run_models import FailureIntelligenceRunManifest

    assert isinstance(manifest, FailureIntelligenceRunManifest)
    _print_json(
        {
            "schema_version": manifest.schema_version,
            "run_id": manifest.run_id,
            "run_dir": str(manifest.run_dir),
            "status": manifest.status,
            "resumed": manifest.resumed,
            "replay_from": manifest.replay_from,
            "stages": [
                {"name": stage.name, "disposition": stage.disposition} for stage in manifest.stages
            ],
            "artifacts": len(manifest.artifacts),
            "failure_report_path": manifest.failure_report_path,
            "failure_report_markdown_path": manifest.failure_report_markdown_path,
            "failure_reason": manifest.failure_reason,
        }
    )


def _print_failure_report_summary(report: object, output: Path, markdown_output: Path) -> None:
    from rtl_agent.failure_report_models import FailureReport

    assert isinstance(report, FailureReport)
    _print_json(
        {
            "schema_version": report.schema_version,
            "output": str(output),
            "markdown_output": str(markdown_output),
            "observed_failure_facts": len(report.observed_failure_facts),
            "earliest_divergence_time": report.earliest_divergence_time,
            "ranked_relevant_signals": len(report.ranked_relevant_signals),
            "candidate_source_locations": len(report.candidate_source_locations),
            "driver_dependency_evidence": len(report.driver_dependency_evidence),
            "unresolved_evidence": len(report.unresolved_evidence),
            "ambiguous_evidence": len(report.ambiguous_evidence),
            "generated_from": len(report.generated_from),
            "warnings": len(report.warnings),
        }
    )


def _print_divergence_graph_summary(report: object, output: Path) -> None:
    from rtl_agent.failure_divergence_graph_models import FailureDivergenceGraphReport

    assert isinstance(report, FailureDivergenceGraphReport)
    _print_json(
        {
            "schema_version": report.schema_version,
            "output": str(output),
            "root_identifiers": report.root_identifiers,
            "global_earliest_divergence_time": report.global_earliest_divergence_time,
            "nodes": len(report.nodes),
            "edges": len(report.edges),
            "unresolved_identifiers": len(report.unresolved_identifiers),
            "truncated": report.truncated,
            "warnings": len(report.warnings),
        }
    )


def _print_driver_trace_summary(report: object, output: Path) -> None:
    from rtl_agent.rtl_driver_trace_models import RtlDriverTraceReport

    assert isinstance(report, RtlDriverTraceReport)
    _print_json(
        {
            "schema_version": report.schema_version,
            "output": str(output),
            "traced_signals": len(report.traced_signals),
            "signals_with_drivers": sum(
                1 for signal in report.traced_signals if signal.status == "traced"
            ),
            "dependency_nodes": len(report.dependency_nodes),
            "dependency_edges": len(report.dependency_edges),
            "unresolved_identifiers": len(report.unresolved_identifiers),
            "truncated": report.truncated,
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
