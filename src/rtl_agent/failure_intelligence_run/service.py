from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from rtl_agent.artifacts import RunStore
from rtl_agent.config import DiscoveryConfig
from rtl_agent.discovery import DiscoveryError, discover_repository, write_repository_map
from rtl_agent.failure_divergence_graph import (
    FailureDivergenceGraphError,
    build_failure_divergence_graph,
    write_divergence_graph,
)
from rtl_agent.failure_intelligence_run_models import (
    FailureIntelligenceRunManifest,
    RunArtifact,
    RunStage,
    RunStatus,
    StageStatus,
)
from rtl_agent.failure_report import (
    FailureReportError,
    synthesize_failure_report,
    write_failure_markdown,
    write_failure_report,
)
from rtl_agent.models import utc_now
from rtl_agent.rtl_driver_trace import RtlDriverTraceError, trace_drivers, write_driver_trace
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
from rtl_agent.waveform import WaveformSliceError, extract_waveform_window, write_waveform_slice
from rtl_agent.waveform_comparison import (
    WaveformComparisonError,
    compare_waveforms,
    write_comparison_report,
)

_STAGE_ERRORS = (
    WaveformSliceError,
    WaveformComparisonError,
    DiscoveryError,
    SignalSourceMapError,
    RtlDriverTraceError,
    FailureDivergenceGraphError,
    SignalReductionError,
    FailureReportError,
    OSError,
    ValueError,
)

_StageResult = tuple[list[RunArtifact], list[str]]


class FailureIntelligenceRunError(RuntimeError):
    pass


class _StageFailed(Exception):
    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(reason)
        self.stage = stage
        self.reason = reason


def run_failure_intelligence(
    run_store: RunStore,
    *,
    failing_vcd: Path,
    passing_vcd: Path,
    repository_root: Path,
    failure_time: int,
    before: int,
    after: int,
    discovery_config: DiscoveryConfig | None = None,
    verification_strength_path: Path | None = None,
    review_path: Path | None = None,
) -> FailureIntelligenceRunManifest:
    run_dir = run_store.run_dir
    for sub in ("waveform", "discovery", "reduction"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)

    failing_slice = run_dir / "waveform" / "failing-slice.json"
    passing_slice = run_dir / "waveform" / "passing-slice.json"
    comparison = run_dir / "waveform" / "comparison.json"
    repository_map = run_dir / "discovery" / "repository-map.json"
    signal_map = run_dir / "signal-source-map.json"
    driver_trace = run_dir / "driver-trace.json"
    divergence_graph = run_dir / "divergence-graph.json"
    reduction_report = run_dir / "reduction" / "report.json"
    reduced_slice = run_dir / "reduction" / "reduced-slice.json"
    failure_report_json = run_dir / "failure-report.json"
    failure_report_md = run_dir / "failure-report.md"

    stages: list[RunStage] = []
    artifacts: list[RunArtifact] = []

    def rel(path: Path) -> str:
        return path.relative_to(run_dir).as_posix()

    def run_stage(name: str, inputs: list[str], action: Callable[[], _StageResult]) -> None:
        start = time.monotonic()
        try:
            produced, warnings = action()
        except _STAGE_ERRORS as exc:
            stages.append(
                RunStage(
                    name=name,
                    status=StageStatus.FAILED,
                    inputs=inputs,
                    outputs=[],
                    duration_seconds=round(time.monotonic() - start, 6),
                    failure_reason=str(exc),
                )
            )
            run_store.append_event(
                "failure_intelligence_stage",
                {"stage": name, "status": "failed", "reason": str(exc)},
            )
            raise _StageFailed(name, str(exc)) from exc
        artifacts.extend(produced)
        outputs = [artifact.relative_path for artifact in produced]
        stages.append(
            RunStage(
                name=name,
                status=StageStatus.COMPLETED,
                inputs=inputs,
                outputs=outputs,
                duration_seconds=round(time.monotonic() - start, 6),
                warnings=warnings,
            )
        )
        run_store.append_event(
            "failure_intelligence_stage",
            {"stage": name, "status": "completed", "outputs": outputs},
        )

    def one[R: BaseModel](
        report: R, path: Path, writer: Callable[[R, Path], None], artifact_id: str, kind: str
    ) -> _StageResult:
        writer(report, path)
        version = getattr(report, "schema_version", None)
        warnings = [str(item) for item in getattr(report, "warnings", []) or []]
        artifact = RunArtifact(
            artifact_id=artifact_id,
            kind=kind,
            relative_path=rel(path),
            schema_version=version if isinstance(version, int) else None,
        )
        return [artifact], warnings

    def reduce_action() -> _StageResult:
        report = reduce_relevant_signals(failing_slice, reduced_slice)
        write_reduction_report(report, reduction_report)
        return (
            [
                RunArtifact(
                    artifact_id="reduction",
                    kind="relevant_signal_reduction_report",
                    relative_path=rel(reduction_report),
                    schema_version=report.schema_version,
                ),
                RunArtifact(
                    artifact_id="reduced-slice",
                    kind="waveform_slice_report",
                    relative_path=rel(reduced_slice),
                    schema_version=_schema_version(reduced_slice),
                ),
            ],
            [str(item) for item in report.warnings],
        )

    def synthesize_action() -> _StageResult:
        report = synthesize_failure_report(
            divergence_graph,
            reduction_path=reduction_report,
            driver_trace_path=driver_trace,
            verification_strength_path=verification_strength_path,
            review_path=review_path,
        )
        write_failure_report(report, failure_report_json)
        write_failure_markdown(report, failure_report_md)
        return (
            [
                RunArtifact(
                    artifact_id="failure-report",
                    kind="failure_report",
                    relative_path=rel(failure_report_json),
                    schema_version=report.schema_version,
                ),
                RunArtifact(
                    artifact_id="failure-report-markdown",
                    kind="failure_report_markdown",
                    relative_path=rel(failure_report_md),
                ),
            ],
            [str(item) for item in report.warnings],
        )

    status = RunStatus.COMPLETED
    failure_reason: str | None = None
    report_json_rel: str | None = None
    report_md_rel: str | None = None
    synthesis_inputs = [rel(divergence_graph), rel(reduction_report), rel(driver_trace)]
    if verification_strength_path is not None:
        synthesis_inputs.append(str(verification_strength_path))
    if review_path is not None:
        synthesis_inputs.append(str(review_path))

    try:
        run_stage(
            "extract-failing",
            [str(failing_vcd)],
            lambda: one(
                extract_waveform_window(failing_vcd, failure_time, before, after),
                failing_slice,
                write_waveform_slice,
                "failing-slice",
                "waveform_slice_report",
            ),
        )
        run_stage(
            "extract-passing",
            [str(passing_vcd)],
            lambda: one(
                extract_waveform_window(passing_vcd, failure_time, before, after),
                passing_slice,
                write_waveform_slice,
                "passing-slice",
                "waveform_slice_report",
            ),
        )
        run_stage(
            "compare-waveforms",
            [rel(failing_slice), rel(passing_slice)],
            lambda: one(
                compare_waveforms(failing_slice, passing_slice),
                comparison,
                write_comparison_report,
                "comparison",
                "waveform_comparison_report",
            ),
        )
        run_stage(
            "inspect-repo",
            [str(repository_root)],
            lambda: one(
                discover_repository(repository_root, discovery_config),
                repository_map,
                write_repository_map,
                "repository-map",
                "discovery_repository_map",
            ),
        )
        run_stage(
            "map-signals",
            [rel(repository_map), rel(comparison)],
            lambda: one(
                map_signals_to_source(repository_map, comparison_path=comparison),
                signal_map,
                write_signal_source_map,
                "signal-source-map",
                "signal_source_map_report",
            ),
        )
        run_stage(
            "trace-drivers",
            [rel(signal_map), rel(repository_map)],
            lambda: one(
                trace_drivers(signal_map, repository_map),
                driver_trace,
                write_driver_trace,
                "driver-trace",
                "rtl_driver_trace_report",
            ),
        )
        run_stage(
            "divergence-graph",
            [rel(comparison), rel(signal_map), rel(driver_trace)],
            lambda: one(
                build_failure_divergence_graph(comparison, signal_map, driver_trace),
                divergence_graph,
                write_divergence_graph,
                "divergence-graph",
                "failure_divergence_graph_report",
            ),
        )
        run_stage("reduce-signals", [rel(failing_slice)], reduce_action)
        run_stage("synthesize-failure-report", synthesis_inputs, synthesize_action)
        report_json_rel = rel(failure_report_json)
        report_md_rel = rel(failure_report_md)
    except _StageFailed as failed:
        status = RunStatus.FAILED
        failure_reason = f"stage '{failed.stage}' failed: {failed.reason}"

    manifest = FailureIntelligenceRunManifest(
        run_id=run_store.run_id,
        run_dir=run_dir.resolve(),
        created_at=utc_now(),
        status=status,
        failing_vcd=failing_vcd.resolve(),
        passing_vcd=passing_vcd.resolve(),
        repository_root=repository_root.resolve(),
        failure_time=failure_time,
        before=before,
        after=after,
        stages=stages,
        artifacts=artifacts,
        failure_report_path=report_json_rel,
        failure_report_markdown_path=report_md_rel,
        failure_reason=failure_reason,
        parser_notes=[
            "This run orchestrates the existing failure-intelligence stages in a fixed sequence "
            "and reuses their services directly; it adds no new analysis behavior.",
            "Completed intermediate artifacts are preserved even when a later stage fails.",
        ],
    )
    write_run_manifest(manifest, run_dir / "run-manifest.json")
    run_store.append_event("failure_intelligence_finished", {"status": str(status)})
    return manifest


def write_run_manifest(manifest: FailureIntelligenceRunManifest, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _schema_version(path: Path) -> int | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if isinstance(raw, dict):
        version = raw.get("schema_version")
        if isinstance(version, int):
            return version
    return None
