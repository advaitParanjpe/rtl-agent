from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from rtl_agent.artifacts import RunStore
from rtl_agent.benchmark_models import (
    BenchmarkCase,
    BenchmarkCaseResult,
    BenchmarkManifest,
    BenchmarkReport,
    BenchmarkStatus,
    BenchmarkStep,
    BenchmarkStepResult,
)
from rtl_agent.config import AgentConfig, load_config
from rtl_agent.execution import CommandRunner
from rtl_agent.models import CommandResult, CommandStatus


class BenchmarkError(RuntimeError):
    pass


def load_benchmark_manifest(path: Path) -> BenchmarkManifest:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BenchmarkError(f"benchmark manifest not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise BenchmarkError(f"invalid benchmark YAML: {path}") from exc
    if not isinstance(raw, dict):
        raise BenchmarkError("benchmark manifest root must be a mapping")
    try:
        return BenchmarkManifest.model_validate(raw)
    except ValidationError as exc:
        raise BenchmarkError(f"invalid benchmark manifest: {exc}") from exc


def run_benchmark_manifest(
    manifest_path: Path,
    run_id: str | None = None,
    command_id_factory: Callable[[str, str, str], str] | None = None,
) -> BenchmarkReport:
    manifest_path = manifest_path.resolve()
    manifest = load_benchmark_manifest(manifest_path)
    run_store = RunStore(_resolve_manifest_path(manifest_path, manifest.run_artifact_dir), run_id)
    run_store.create()
    run_store.append_event(
        "benchmark_started",
        {"manifest": str(manifest_path), "name": manifest.name},
    )
    case_results = [
        _run_case(manifest_path, manifest, case, run_store, command_id_factory)
        for case in manifest.cases
    ]
    report = _build_report(manifest_path, manifest, run_store, case_results)
    output = run_store.run_dir / "benchmarks" / "report.json"
    write_benchmark_report(report, output)
    run_store.append_event(
        "benchmark_finished",
        {"status": report.status, "report": str(output), "summary": report.summary},
    )
    return report


def write_benchmark_report(report: BenchmarkReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _run_case(
    manifest_path: Path,
    manifest: BenchmarkManifest,
    case: BenchmarkCase,
    run_store: RunStore,
    command_id_factory: Callable[[str, str, str], str] | None,
) -> BenchmarkCaseResult:
    step_results: list[BenchmarkStepResult] = []
    for step in case.steps:
        step_results.append(
            _run_step(manifest_path, manifest, case.case_id, step, run_store, command_id_factory)
        )
    status = _aggregate_status([result.observed_status for result in step_results])
    expectation_met = all(result.expectation_met for result in step_results)
    if not expectation_met and status == BenchmarkStatus.PASSED:
        status = BenchmarkStatus.FAILED
    return BenchmarkCaseResult(
        case_id=case.case_id,
        status=status,
        expectation_met=expectation_met,
        step_results=step_results,
    )


def _run_step(
    manifest_path: Path,
    manifest: BenchmarkManifest,
    case_id: str,
    step: BenchmarkStep,
    run_store: RunStore,
    command_id_factory: Callable[[str, str, str], str] | None,
) -> BenchmarkStepResult:
    started = time.monotonic()
    try:
        config = _load_step_config(manifest_path, manifest, step)
        deterministic_command_id = (
            (lambda command_name: command_id_factory(case_id, step.step_id, command_name))
            if command_id_factory
            else None
        )
        runner = CommandRunner(config, run_store, command_id_factory=deterministic_command_id)
        command_result = runner.run_named(step.command)
    except (BenchmarkError, KeyError, ValueError) as exc:
        duration = time.monotonic() - started
        return BenchmarkStepResult(
            case_id=case_id,
            step_id=step.step_id,
            kind=step.kind,
            command_name=step.command,
            expected_status=step.expected_status,
            observed_status=BenchmarkStatus.INFRASTRUCTURE_ERROR,
            expectation_met=step.expected_status == BenchmarkStatus.INFRASTRUCTURE_ERROR,
            duration_seconds=duration,
            failure_summary=str(exc),
        )

    observed = _status_from_command(command_result.status)
    command_result_path = run_store.run_dir / "commands" / command_result.command_id / "result.json"
    return BenchmarkStepResult(
        case_id=case_id,
        step_id=step.step_id,
        kind=step.kind,
        command_name=step.command,
        expected_status=step.expected_status,
        observed_status=observed,
        expectation_met=observed == step.expected_status,
        duration_seconds=command_result.duration_seconds,
        command_result_path=command_result_path,
        stdout_path=command_result.stdout_path,
        stderr_path=command_result.stderr_path,
        failure_summary=_failure_summary(step, observed, command_result),
    )


def _load_step_config(
    manifest_path: Path, manifest: BenchmarkManifest, step: BenchmarkStep
) -> AgentConfig:
    config_path = _resolve_manifest_path(manifest_path, step.config)
    try:
        config = load_config(config_path)
    except ValueError as exc:
        raise BenchmarkError(f"could not load step config {config_path}: {exc}") from exc
    if step.command not in config.commands:
        raise BenchmarkError(f"unknown command for benchmark step: {step.command}")
    command = config.commands[step.command]
    effective_timeout = (
        step.timeout_seconds or command.timeout_seconds or config.execution.timeout_seconds
    )
    if effective_timeout > manifest.resources.max_step_timeout_seconds:
        raise BenchmarkError(
            f"step {step.step_id} effective timeout {effective_timeout}s exceeds "
            f"manifest max {manifest.resources.max_step_timeout_seconds}s"
        )
    if step.timeout_seconds is not None:
        config.commands[step.command] = command.model_copy(
            update={"timeout_seconds": step.timeout_seconds}
        )
    return config


def _build_report(
    manifest_path: Path,
    manifest: BenchmarkManifest,
    run_store: RunStore,
    case_results: list[BenchmarkCaseResult],
) -> BenchmarkReport:
    status = _aggregate_status([result.status for result in case_results])
    if (
        not all(result.expectation_met for result in case_results)
        and status == BenchmarkStatus.PASSED
    ):
        status = BenchmarkStatus.FAILED
    counts = {
        BenchmarkStatus.PASSED: 0,
        BenchmarkStatus.FAILED: 0,
        BenchmarkStatus.TIMEOUT: 0,
        BenchmarkStatus.INFRASTRUCTURE_ERROR: 0,
    }
    for result in case_results:
        counts[result.status] += 1
    return BenchmarkReport(
        manifest_path=manifest_path,
        manifest_name=manifest.name,
        run_id=run_store.run_id,
        run_dir=run_store.run_dir,
        status=status,
        cases_total=len(case_results),
        cases_passed=counts[BenchmarkStatus.PASSED],
        cases_failed=counts[BenchmarkStatus.FAILED],
        cases_timeout=counts[BenchmarkStatus.TIMEOUT],
        cases_infrastructure_error=counts[BenchmarkStatus.INFRASTRUCTURE_ERROR],
        case_results=case_results,
        summary=(
            f"{status} benchmark run with {counts[BenchmarkStatus.PASSED]} passed, "
            f"{counts[BenchmarkStatus.FAILED]} failed, "
            f"{counts[BenchmarkStatus.TIMEOUT]} timeout, and "
            f"{counts[BenchmarkStatus.INFRASTRUCTURE_ERROR]} infrastructure-error case(s)"
        ),
    )


def _aggregate_status(statuses: list[BenchmarkStatus]) -> BenchmarkStatus:
    if any(status == BenchmarkStatus.INFRASTRUCTURE_ERROR for status in statuses):
        return BenchmarkStatus.INFRASTRUCTURE_ERROR
    if any(status == BenchmarkStatus.TIMEOUT for status in statuses):
        return BenchmarkStatus.TIMEOUT
    if any(status == BenchmarkStatus.FAILED for status in statuses):
        return BenchmarkStatus.FAILED
    return BenchmarkStatus.PASSED


def _status_from_command(status: CommandStatus | str) -> BenchmarkStatus:
    if status == CommandStatus.PASSED or status == "passed":
        return BenchmarkStatus.PASSED
    if status == CommandStatus.FAILED or status == "failed":
        return BenchmarkStatus.FAILED
    if status == CommandStatus.TIMEOUT or status == "timeout":
        return BenchmarkStatus.TIMEOUT
    return BenchmarkStatus.INFRASTRUCTURE_ERROR


def _failure_summary(
    step: BenchmarkStep, observed: BenchmarkStatus, command_result: CommandResult
) -> str | None:
    if observed == step.expected_status:
        return None
    details = (
        f"expected {step.expected_status}, observed {observed}; "
        f"exit_code={command_result.exit_code}"
    )
    if command_result.error:
        return f"{details}; error={command_result.error}"
    return details


def _resolve_manifest_path(manifest_path: Path, path: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (manifest_path.parent / path).resolve()


def report_output_path(report: BenchmarkReport) -> Path:
    return report.run_dir / "benchmarks" / "report.json"


def report_summary_payload(report: BenchmarkReport) -> dict[str, Any]:
    return {
        "schema_version": report.schema_version,
        "manifest_name": report.manifest_name,
        "run_id": report.run_id,
        "status": report.status,
        "output": str(report_output_path(report)),
        "cases_total": report.cases_total,
        "cases_passed": report.cases_passed,
        "cases_failed": report.cases_failed,
        "cases_timeout": report.cases_timeout,
        "cases_infrastructure_error": report.cases_infrastructure_error,
        "summary": report.summary,
    }
