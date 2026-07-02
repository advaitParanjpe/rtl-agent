from __future__ import annotations

import json
from pathlib import Path

import pytest

from rtl_agent.benchmark import (
    BenchmarkError,
    load_benchmark_manifest,
    run_benchmark_manifest,
    write_benchmark_report,
)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_config(tmp_path: Path) -> Path:
    config = tmp_path / "rtl-agent.yaml"
    write(
        config,
        f"""
schema_version: 1
repository_path: .
run_artifact_dir: {tmp_path / ".rtl-agent" / "runs"}
allowed_working_paths: [.]
execution:
  timeout_seconds: 5
commands:
  pass:
    argv: [python3, -c, "print('ok')"]
    cwd: .
    timeout_seconds: 5
  fail:
    argv: [python3, -c, "raise SystemExit(3)"]
    cwd: .
    timeout_seconds: 5
  slow:
    argv: [python3, -c, "import time; time.sleep(2)"]
    cwd: .
    timeout_seconds: 5
""",
    )
    return config


def make_manifest(
    tmp_path: Path, config: Path, command: str = "pass", expected_status: str = "passed"
) -> Path:
    manifest = tmp_path / "benchmark.yaml"
    write(
        manifest,
        f"""
schema_version: 1
name: unit-benchmark
run_artifact_dir: .rtl-agent/runs
resources:
  max_cases: 3
  max_steps_per_case: 2
  max_step_timeout_seconds: 5
cases:
  - case_id: case-1
    steps:
      - step_id: step-1
        kind: named_command
        config: {config.name}
        command: {command}
        expected_status: {expected_status}
        timeout_seconds: 5
""",
    )
    return manifest


def test_load_benchmark_manifest_requires_declared_bounds(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    manifest_path = make_manifest(tmp_path, config)

    manifest = load_benchmark_manifest(manifest_path)

    assert manifest.name == "unit-benchmark"
    assert manifest.resources.max_cases == 3
    assert manifest.cases[0].steps[0].expected_status == "passed"


def test_benchmark_report_is_stable_json_for_same_report(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    manifest_path = make_manifest(tmp_path, config)
    report = run_benchmark_manifest(
        manifest_path,
        run_id="run-1",
        command_id_factory=lambda case_id, step_id, command: f"{case_id}-{step_id}-{command}",
    )
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    write_benchmark_report(report, first)
    write_benchmark_report(report, second)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    assert json.loads(first.read_text(encoding="utf-8"))["schema_version"] == 1


def test_failing_step_records_failed_result_and_artifact_paths(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    manifest_path = make_manifest(tmp_path, config, command="fail", expected_status="passed")

    report = run_benchmark_manifest(
        manifest_path,
        run_id="run-1",
        command_id_factory=lambda case_id, step_id, command: f"{case_id}-{step_id}-{command}",
    )

    step = report.case_results[0].step_results[0]
    assert report.status == "failed"
    assert step.observed_status == "failed"
    assert step.expectation_met is False
    assert step.command_result_path is not None
    assert step.command_result_path.exists()
    assert step.failure_summary is not None


def test_timeout_step_records_timeout_result(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    manifest_path = make_manifest(tmp_path, config, command="slow", expected_status="passed")
    data = manifest_path.read_text(encoding="utf-8").replace(
        "timeout_seconds: 5", "timeout_seconds: 1"
    )
    manifest_path.write_text(data, encoding="utf-8")

    report = run_benchmark_manifest(
        manifest_path,
        run_id="run-1",
        command_id_factory=lambda case_id, step_id, command: f"{case_id}-{step_id}-{command}",
    )

    assert report.status == "timeout"
    assert report.case_results[0].step_results[0].observed_status == "timeout"


def test_unknown_command_records_infrastructure_error(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    manifest_path = make_manifest(tmp_path, config, command="missing", expected_status="passed")

    report = run_benchmark_manifest(manifest_path, run_id="run-1")

    step = report.case_results[0].step_results[0]
    assert report.status == "infrastructure_error"
    assert step.observed_status == "infrastructure_error"
    assert "unknown command" in str(step.failure_summary)


def test_manifest_rejects_resource_bound_violations(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    manifest_path = make_manifest(tmp_path, config)
    text = manifest_path.read_text(encoding="utf-8").replace(
        "max_step_timeout_seconds: 5", "max_step_timeout_seconds: 1"
    )
    manifest_path.write_text(text, encoding="utf-8")

    with pytest.raises(BenchmarkError, match="invalid benchmark manifest"):
        load_benchmark_manifest(manifest_path)
