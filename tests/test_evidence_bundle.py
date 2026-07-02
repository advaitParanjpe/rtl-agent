from __future__ import annotations

import json
from pathlib import Path

from rtl_agent.artifacts import RunStore
from rtl_agent.evidence_bundle import export_evidence_bundle, write_evidence_bundle_report
from rtl_agent.models import CommandResult, CommandStatus, utc_now


def make_run(tmp_path: Path) -> Path:
    store = RunStore(tmp_path / ".rtl-agent" / "runs", run_id="run-1")
    store.create()
    command_dir = store.command_dir("smoke-1")
    stdout_path = command_dir / "stdout.log"
    stderr_path = command_dir / "stderr.log"
    stdout_path.write_text("hello\n", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    now = utc_now()
    result = CommandResult(
        command_id="smoke-1",
        command_name="smoke",
        argv=["python3", "-c", "print('hello')"],
        cwd=tmp_path,
        status=CommandStatus.PASSED,
        started_at=now,
        ended_at=now,
        duration_seconds=0,
        exit_code=0,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
    store.write_command_result(command_dir, result)
    benchmark_dir = store.run_dir / "benchmarks"
    benchmark_dir.mkdir()
    (benchmark_dir / "report.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_path": "benchmark.yaml",
                "manifest_name": "unit",
                "run_id": "run-1",
                "run_dir": str(store.run_dir),
                "status": "passed",
                "cases_total": 0,
                "cases_passed": 0,
                "cases_failed": 0,
                "cases_timeout": 0,
                "cases_infrastructure_error": 0,
                "case_results": [],
                "summary": "passed",
            }
        ),
        encoding="utf-8",
    )
    return store.run_dir


def test_evidence_bundle_export_is_stable_json_for_same_inputs(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    report = export_evidence_bundle(run_dir, tmp_path / "bundle")
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    write_evidence_bundle_report(report, first)
    write_evidence_bundle_report(report, second)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["status"] == "passed"


def test_evidence_bundle_records_hashes_schema_versions_and_omitted_logs(
    tmp_path: Path,
) -> None:
    run_dir = make_run(tmp_path)

    report = export_evidence_bundle(run_dir, tmp_path / "bundle")

    by_path = {artifact.relative_path: artifact for artifact in report.artifacts}
    assert by_path["run.json"].schema_version == 1
    assert by_path["run.json"].sha256 is not None
    assert by_path["commands/smoke-1/result.json"].kind == "command_result"
    assert by_path["commands/smoke-1/stdout.log"].included_in_bundle is False
    assert by_path["commands/smoke-1/stdout.log"].omitted_reason is not None
    assert "referenced only" in by_path["commands/smoke-1/stdout.log"].omitted_reason


def test_evidence_bundle_warns_on_missing_optional_artifacts(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)

    report = export_evidence_bundle(run_dir, tmp_path / "bundle")

    assert report.status == "passed"
    assert any("implementation/report.json" in warning for warning in report.warnings)
    assert any("discovery/repository-map.json" in warning for warning in report.warnings)


def test_evidence_bundle_failed_when_run_metadata_missing(tmp_path: Path) -> None:
    run_dir = tmp_path / ".rtl-agent" / "runs" / "run-1"
    run_dir.mkdir(parents=True)

    report = export_evidence_bundle(run_dir, tmp_path / "bundle")

    assert report.status == "failed"
    assert report.failure_reason is not None
    assert "run.json" in report.failure_reason
    assert (tmp_path / "bundle" / "bundle.json").exists()


def test_evidence_bundle_does_not_mutate_source_artifacts(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    stdout_path = run_dir / "commands" / "smoke-1" / "stdout.log"
    before = stdout_path.read_text(encoding="utf-8")

    export_evidence_bundle(run_dir, tmp_path / "bundle")

    assert stdout_path.read_text(encoding="utf-8") == before
