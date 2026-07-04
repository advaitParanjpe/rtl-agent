from __future__ import annotations

import json
from pathlib import Path

from rtl_agent.artifacts import RunStore
from rtl_agent.assertion_link import link_assertion_to_waveform, write_link_report
from rtl_agent.evidence_bundle import export_evidence_bundle, write_evidence_bundle_report
from rtl_agent.failure_divergence_graph_models import FailureDivergenceGraphReport
from rtl_agent.models import CommandResult, CommandStatus, utc_now
from rtl_agent.relevant_signal_models import RelevantSignalReductionReport
from rtl_agent.rtl_driver_trace_models import RtlDriverTraceReport
from rtl_agent.signal_source_map_models import SignalSourceMapReport
from rtl_agent.waveform import extract_waveform_window, write_waveform_slice
from rtl_agent.waveform_comparison_models import (
    ComparisonTimeBasis,
    TimeBasisKind,
    WaveformComparisonReport,
)

FIXTURE_VCD = Path("examples/waveforms/failure.vcd")
FIXTURE_TRIAGE = Path("examples/waveforms/triage-report.json")


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


def add_waveform_artifacts(run_dir: Path) -> None:
    waveform_dir = run_dir / "waveform"
    slice_report = extract_waveform_window(FIXTURE_VCD, failure_time=40, before=15, after=5)
    write_waveform_slice(slice_report, waveform_dir / "slice.json")
    link_report = link_assertion_to_waveform(
        FIXTURE_TRIAGE,
        waveform_dir / "assertion-link-slice.json",
        assertion_id="assertion-0",
        before=15,
        after=5,
    )
    write_link_report(link_report, waveform_dir / "assertion-link.json")


def test_evidence_bundle_classifies_waveform_and_assertion_link_artifacts(
    tmp_path: Path,
) -> None:
    run_dir = make_run(tmp_path)
    add_waveform_artifacts(run_dir)

    report = export_evidence_bundle(run_dir, tmp_path / "bundle")

    by_path = {artifact.relative_path: artifact for artifact in report.artifacts}
    slice_artifact = by_path["waveform/slice.json"]
    assert slice_artifact.kind == "waveform_slice_report"
    assert slice_artifact.schema_version == 1
    assert slice_artifact.sha256 is not None
    link_artifact = by_path["waveform/assertion-link.json"]
    assert link_artifact.kind == "assertion_waveform_link_report"
    assert link_artifact.schema_version == 1
    assert link_artifact.sha256 is not None
    # The link's generated slice is still classified as a waveform slice.
    assert by_path["waveform/assertion-link-slice.json"].kind == "waveform_slice_report"


def test_evidence_bundle_with_waveform_artifacts_is_deterministic(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    add_waveform_artifacts(run_dir)

    report = export_evidence_bundle(run_dir, tmp_path / "bundle")
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    write_evidence_bundle_report(report, first)
    write_evidence_bundle_report(report, second)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")


def add_failure_intelligence_artifacts(run_dir: Path) -> None:
    failure_dir = run_dir / "failure"
    failure_dir.mkdir()

    def dump(name: str, model: object) -> None:
        (failure_dir / name).write_text(
            json.dumps(model.model_dump(mode="json")),  # type: ignore[attr-defined]
            encoding="utf-8",
        )

    dump(
        "reduction.json",
        RelevantSignalReductionReport(
            waveform_slice_path=run_dir / "slice.json",
            failure_time=40,
            max_signals=32,
            total_candidate_signals=4,
            reduced_slice_path=run_dir / "reduced.json",
            reduced_slice_sha256="0" * 64,
        ),
    )
    dump(
        "comparison.json",
        WaveformComparisonReport(
            failing_slice_path=run_dir / "f.json",
            passing_slice_path=run_dir / "p.json",
            time_basis=ComparisonTimeBasis(
                kind=TimeBasisKind.SHARED_TICKS,
                normalized=False,
                common_start=0,
                common_end=10,
                detail="shared",
            ),
            shared_signal_count=0,
        ),
    )
    dump(
        "signal-source-map.json",
        SignalSourceMapReport(
            repository_map_path=run_dir / "repo-map.json",
            total_signals=0,
            exact_count=0,
            probable_count=0,
            ambiguous_count=0,
            unresolved_count=0,
        ),
    )
    dump(
        "driver-trace.json",
        RtlDriverTraceReport(
            signal_source_map_path=run_dir / "signal-source-map.json",
            repository_map_path=run_dir / "repo-map.json",
            repository_root=run_dir / "repo",
            max_depth=2,
            max_nodes=64,
        ),
    )
    dump(
        "divergence-graph.json",
        FailureDivergenceGraphReport(
            comparison_path=run_dir / "comparison.json",
            signal_source_map_path=run_dir / "signal-source-map.json",
            driver_trace_path=run_dir / "driver-trace.json",
            max_depth=3,
            max_nodes=128,
        ),
    )


def test_evidence_bundle_classifies_failure_intelligence_artifacts(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    add_failure_intelligence_artifacts(run_dir)

    report = export_evidence_bundle(run_dir, tmp_path / "bundle")

    by_path = {artifact.relative_path: artifact for artifact in report.artifacts}
    expected = {
        "failure/reduction.json": "relevant_signal_reduction_report",
        "failure/comparison.json": "waveform_comparison_report",
        "failure/signal-source-map.json": "signal_source_map_report",
        "failure/driver-trace.json": "rtl_driver_trace_report",
        "failure/divergence-graph.json": "failure_divergence_graph_report",
    }
    for relative_path, kind in expected.items():
        artifact = by_path[relative_path]
        assert artifact.kind == kind, relative_path
        assert artifact.schema_version == 1
        assert artifact.sha256 is not None


def test_evidence_bundle_with_failure_intelligence_is_deterministic(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    add_failure_intelligence_artifacts(run_dir)

    report = export_evidence_bundle(run_dir, tmp_path / "bundle")
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_evidence_bundle_report(report, first)
    write_evidence_bundle_report(report, second)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")


def test_evidence_bundle_does_not_mutate_source_artifacts(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    stdout_path = run_dir / "commands" / "smoke-1" / "stdout.log"
    before = stdout_path.read_text(encoding="utf-8")

    export_evidence_bundle(run_dir, tmp_path / "bundle")

    assert stdout_path.read_text(encoding="utf-8") == before
