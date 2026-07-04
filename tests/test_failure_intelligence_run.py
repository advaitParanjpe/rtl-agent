from __future__ import annotations

from pathlib import Path

from test_failure_report import make_review, make_verification

from rtl_agent.artifacts import RunStore
from rtl_agent.failure_intelligence_run import run_failure_intelligence
from rtl_agent.failure_intelligence_run_models import FailureIntelligenceRunManifest
from rtl_agent.failure_report_models import FailureReport
from rtl_agent.waveform_comparison_models import WaveformComparisonReport

FAILING_VCD = Path("examples/waveforms/failure.vcd")
PASSING_VCD = Path("examples/waveforms/passing.vcd")
SIMPLE_RTL = Path("examples/simple-rtl")

STAGE_NAMES = [
    "extract-failing",
    "extract-passing",
    "compare-waveforms",
    "inspect-repo",
    "map-signals",
    "trace-drivers",
    "divergence-graph",
    "reduce-signals",
    "synthesize-failure-report",
]


def run(
    tmp_path: Path,
    run_id: str,
    *,
    passing: Path = PASSING_VCD,
    verification_strength_path: Path | None = None,
    review_path: Path | None = None,
) -> FailureIntelligenceRunManifest:
    store = RunStore(tmp_path / "runs", run_id=run_id)
    store.create()
    return run_failure_intelligence(
        store,
        failing_vcd=FAILING_VCD,
        passing_vcd=passing,
        repository_root=SIMPLE_RTL,
        failure_time=40,
        before=15,
        after=15,
        verification_strength_path=verification_strength_path,
        review_path=review_path,
    )


def test_successful_run_completes_all_stages(tmp_path: Path) -> None:
    manifest = run(tmp_path, "run-a")

    assert manifest.status == "completed"
    assert [stage.name for stage in manifest.stages] == STAGE_NAMES
    assert all(stage.status == "completed" for stage in manifest.stages)
    assert manifest.failure_reason is None
    assert manifest.failure_report_path == "failure-report.json"
    assert manifest.failure_report_markdown_path == "failure-report.md"
    assert manifest.schema_version == 1


def test_all_artifacts_placed_under_run_dir(tmp_path: Path) -> None:
    manifest = run(tmp_path, "run-a")

    run_dir = tmp_path / "runs" / "run-a"
    assert manifest.artifacts
    for artifact in manifest.artifacts:
        assert (run_dir / artifact.relative_path).exists(), artifact.relative_path
    # The report content validates through its typed model.
    report = FailureReport.model_validate_json(
        (run_dir / "failure-report.json").read_text(encoding="utf-8")
    )
    assert {fact.identifier for fact in report.observed_failure_facts} == {"state", "valid"}
    comparison = WaveformComparisonReport.model_validate_json(
        (run_dir / "waveform" / "comparison.json").read_text(encoding="utf-8")
    )
    assert {s.name for s in comparison.diverging_signals} == {"top.dut.state", "top.dut.valid"}


def test_manifest_and_run_files_present(tmp_path: Path) -> None:
    run(tmp_path, "run-a")

    run_dir = tmp_path / "runs" / "run-a"
    assert (run_dir / "run-manifest.json").exists()
    assert (run_dir / "run.json").exists()
    assert (run_dir / "events.jsonl").exists()


def test_stage_failure_stops_and_preserves_completed_artifacts(tmp_path: Path) -> None:
    bad = tmp_path / "bad.vcd"
    bad.write_text("not a vcd", encoding="utf-8")

    manifest = run(tmp_path, "run-fail", passing=bad)

    assert manifest.status == "failed"
    assert manifest.failure_reason is not None
    assert "extract-passing" in manifest.failure_reason
    names = [stage.name for stage in manifest.stages]
    assert names == ["extract-failing", "extract-passing"]  # stopped after the failure
    assert manifest.stages[0].status == "completed"
    assert manifest.stages[1].status == "failed"
    assert manifest.failure_report_path is None
    run_dir = tmp_path / "runs" / "run-fail"
    # The completed stage's artifact is preserved despite the later failure.
    assert (run_dir / "waveform" / "failing-slice.json").exists()
    assert (run_dir / "run-manifest.json").exists()


def test_stage_artifacts_are_deterministic(tmp_path: Path) -> None:
    run(tmp_path, "run-a")
    run(tmp_path, "run-b")

    a = tmp_path / "runs" / "run-a"
    b = tmp_path / "runs" / "run-b"
    for relative in ("waveform/failing-slice.json", "reduction/reduced-slice.json"):
        assert (a / relative).read_text(encoding="utf-8") == (b / relative).read_text(
            encoding="utf-8"
        ), relative


def test_optional_inputs_flow_into_report(tmp_path: Path) -> None:
    manifest = run(
        tmp_path,
        "run-opt",
        verification_strength_path=make_verification(tmp_path),
        review_path=make_review(tmp_path),
    )

    run_dir = tmp_path / "runs" / "run-opt"
    report = FailureReport.model_validate_json(
        (run_dir / "failure-report.json").read_text(encoding="utf-8")
    )
    assert report.verification_status is not None
    assert report.verification_status.strength == "insufficient"
    assert report.review_status is not None
    assert report.review_status.outcome == "unacceptable"
    synth_stage = next(s for s in manifest.stages if s.name == "synthesize-failure-report")
    assert any("vs.json" in item for item in synth_stage.inputs)


def test_artifact_kinds_recorded(tmp_path: Path) -> None:
    manifest = run(tmp_path, "run-a")

    kinds = {artifact.kind for artifact in manifest.artifacts}
    assert {
        "waveform_slice_report",
        "waveform_comparison_report",
        "discovery_repository_map",
        "signal_source_map_report",
        "rtl_driver_trace_report",
        "failure_divergence_graph_report",
        "relevant_signal_reduction_report",
        "failure_report",
    } <= kinds
