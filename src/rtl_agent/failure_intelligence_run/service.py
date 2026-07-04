from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError

from rtl_agent.artifacts import RunStore
from rtl_agent.config import DiscoveryConfig
from rtl_agent.discovery import DiscoveryError, discover_repository, write_repository_map
from rtl_agent.failure_divergence_graph import (
    FailureDivergenceGraphError,
    build_failure_divergence_graph,
    write_divergence_graph,
)
from rtl_agent.failure_divergence_graph_models import (
    FAILURE_DIVERGENCE_GRAPH_SCHEMA_VERSION,
    FailureDivergenceGraphReport,
)
from rtl_agent.failure_intelligence_run_models import (
    FailureIntelligenceRunManifest,
    RunArtifact,
    RunStage,
    RunStatus,
    StageDisposition,
)
from rtl_agent.failure_report import (
    FailureReportError,
    synthesize_failure_report,
    write_failure_markdown,
    write_failure_report,
)
from rtl_agent.failure_report_models import FAILURE_REPORT_SCHEMA_VERSION, FailureReport
from rtl_agent.models import utc_now
from rtl_agent.relevant_signal_models import (
    RELEVANT_SIGNAL_REDUCTION_SCHEMA_VERSION,
    RelevantSignalReductionReport,
)
from rtl_agent.repository_map import REPOSITORY_MAP_SCHEMA_VERSION, RepositoryMap
from rtl_agent.rtl_driver_trace import RtlDriverTraceError, trace_drivers, write_driver_trace
from rtl_agent.rtl_driver_trace_models import RTL_DRIVER_TRACE_SCHEMA_VERSION, RtlDriverTraceReport
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
from rtl_agent.signal_source_map_models import (
    SIGNAL_SOURCE_MAP_SCHEMA_VERSION,
    SignalSourceMapReport,
)
from rtl_agent.waveform import WaveformSliceError, extract_waveform_window, write_waveform_slice
from rtl_agent.waveform_comparison import (
    WaveformComparisonError,
    compare_waveforms,
    write_comparison_report,
)
from rtl_agent.waveform_comparison_models import (
    WAVEFORM_COMPARISON_SCHEMA_VERSION,
    WaveformComparisonReport,
)
from rtl_agent.waveform_slice_models import WAVEFORM_SLICE_SCHEMA_VERSION, WaveformSliceReport

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


class FailureIntelligenceRunError(RuntimeError):
    pass


@dataclass(frozen=True)
class _Output:
    artifact_id: str
    kind: str
    path: Path
    model: type[BaseModel] | None = None
    schema_version: int | None = None


@dataclass
class _Stage:
    name: str
    inputs: list[str]
    outputs: list[_Output]
    action: Callable[[], list[str]]


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
    resume: bool = False,
    replay_from: str | None = None,
) -> FailureIntelligenceRunManifest:
    run_dir = run_store.run_dir
    for sub in ("waveform", "discovery", "reduction"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)

    stages = _build_stages(
        run_dir,
        failing_vcd=failing_vcd,
        passing_vcd=passing_vcd,
        repository_root=repository_root,
        failure_time=failure_time,
        before=before,
        after=after,
        discovery_config=discovery_config,
        verification_strength_path=verification_strength_path,
        review_path=review_path,
    )
    stage_names = [stage.name for stage in stages]

    replay_index: int | None = None
    if replay_from is not None:
        if replay_from not in stage_names:
            raise FailureIntelligenceRunError(
                f"unknown replay stage: {replay_from} (choose from {', '.join(stage_names)})"
            )
        replay_index = stage_names.index(replay_from)

    warnings: list[str] = []
    prior = _load_prior_manifest(run_dir) if (resume or replay_from is not None) else None
    reusable = prior is not None and _inputs_match(
        prior, failing_vcd, passing_vcd, repository_root, failure_time, before, after
    )
    if (resume or replay_from is not None) and prior is None:
        warnings.append("no prior run manifest to resume; all stages will run")
    elif prior is not None and not reusable:
        warnings.append("prior run inputs differ from current inputs; all stages will regenerate")
    prior_dispositions, prior_artifacts = _prior_index(prior)

    recorded_stages: list[RunStage] = []
    artifacts: list[RunArtifact] = []
    upstream_changed = not reusable
    run_stopped = False
    report_json_rel: str | None = None
    report_md_rel: str | None = None

    for index, stage in enumerate(stages):
        if run_stopped:
            recorded_stages.append(
                RunStage(
                    name=stage.name,
                    disposition=StageDisposition.SKIPPED,
                    reason="an earlier stage failed",
                    inputs=stage.inputs,
                    outputs=[],
                    duration_seconds=0.0,
                )
            )
            run_store.append_event(
                "failure_intelligence_stage",
                {"stage": stage.name, "disposition": "skipped", "reason": "earlier stage failed"},
            )
            continue

        forced = replay_index is not None and index >= replay_index
        start = time.monotonic()

        if reusable and not upstream_changed and not forced:
            ok, reason = _validate_reuse(run_dir, stage, prior_artifacts)
            if ok:
                stage_artifacts = _collect_artifacts(run_dir, stage)
                artifacts.extend(stage_artifacts)
                recorded_stages.append(
                    RunStage(
                        name=stage.name,
                        disposition=StageDisposition.REUSED,
                        reason="existing artifact validated (existence, sha256, schema, inputs)",
                        inputs=stage.inputs,
                        outputs=[a.relative_path for a in stage_artifacts],
                        duration_seconds=round(time.monotonic() - start, 6),
                    )
                )
                run_store.append_event(
                    "failure_intelligence_stage",
                    {"stage": stage.name, "disposition": "reused"},
                )
                continue
            warnings.append(f"stage '{stage.name}' regenerated: {reason}")
            regen_reason = reason
        elif forced:
            regen_reason = "replay requested from this stage"
        else:
            regen_reason = "upstream stage changed"

        _invalidate_outputs(stage)
        prior_produced = prior_dispositions.get(stage.name) in {"executed", "reused", "regenerated"}
        try:
            stage_warnings = stage.action()
        except _STAGE_ERRORS as exc:
            recorded_stages.append(
                RunStage(
                    name=stage.name,
                    disposition=StageDisposition.FAILED,
                    reason=None,
                    inputs=stage.inputs,
                    outputs=[],
                    duration_seconds=round(time.monotonic() - start, 6),
                    failure_reason=str(exc),
                )
            )
            run_store.append_event(
                "failure_intelligence_stage",
                {"stage": stage.name, "disposition": "failed", "reason": str(exc)},
            )
            run_stopped = True
            continue

        upstream_changed = True
        disposition = StageDisposition.REGENERATED if prior_produced else StageDisposition.EXECUTED
        stage_artifacts = _collect_artifacts(run_dir, stage)
        artifacts.extend(stage_artifacts)
        recorded_stages.append(
            RunStage(
                name=stage.name,
                disposition=disposition,
                reason=regen_reason if disposition == StageDisposition.REGENERATED else None,
                inputs=stage.inputs,
                outputs=[a.relative_path for a in stage_artifacts],
                duration_seconds=round(time.monotonic() - start, 6),
                warnings=stage_warnings,
            )
        )
        run_store.append_event(
            "failure_intelligence_stage",
            {"stage": stage.name, "disposition": str(disposition), "reason": regen_reason},
        )
        if stage.name == "synthesize-failure-report":
            report_json_rel = "failure-report.json"
            report_md_rel = "failure-report.md"

    if run_stopped:
        status = RunStatus.FAILED
        failed = next(s for s in recorded_stages if s.disposition == StageDisposition.FAILED)
        failure_reason: str | None = f"stage '{failed.name}' failed: {failed.failure_reason}"
    else:
        status = RunStatus.COMPLETED
        failure_reason = None
        if report_json_rel is None:
            report_json_rel = "failure-report.json"
            report_md_rel = "failure-report.md"

    manifest = FailureIntelligenceRunManifest(
        run_id=run_store.run_id,
        run_dir=run_dir.resolve(),
        created_at=utc_now(),
        status=status,
        resumed=resume,
        replay_from=replay_from,
        failing_vcd=failing_vcd.resolve(),
        passing_vcd=passing_vcd.resolve(),
        repository_root=repository_root.resolve(),
        failure_time=failure_time,
        before=before,
        after=after,
        stages=recorded_stages,
        artifacts=artifacts,
        failure_report_path=report_json_rel,
        failure_report_markdown_path=report_md_rel,
        failure_reason=failure_reason,
        warnings=sorted(dict.fromkeys(warnings)),
        parser_notes=[
            "This run orchestrates the existing failure-intelligence stages in a fixed sequence "
            "and reuses their services directly; it adds no new analysis behavior.",
            "Reused artifacts are validated (existence, recorded sha256, typed model, schema "
            "version, and matching run inputs) before being trusted; regeneration cascades to "
            "downstream stages and completed artifacts are preserved on failure.",
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


def _build_stages(
    run_dir: Path,
    *,
    failing_vcd: Path,
    passing_vcd: Path,
    repository_root: Path,
    failure_time: int,
    before: int,
    after: int,
    discovery_config: DiscoveryConfig | None,
    verification_strength_path: Path | None,
    review_path: Path | None,
) -> list[_Stage]:
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

    def rel(path: Path) -> str:
        return path.relative_to(run_dir).as_posix()

    def write[R: BaseModel](report: R, path: Path, writer: Callable[[R, Path], None]) -> list[str]:
        writer(report, path)
        return [str(item) for item in getattr(report, "warnings", []) or []]

    def act_extract_failing() -> list[str]:
        report = extract_waveform_window(failing_vcd, failure_time, before, after)
        return write(report, failing_slice, write_waveform_slice)

    def act_extract_passing() -> list[str]:
        report = extract_waveform_window(passing_vcd, failure_time, before, after)
        return write(report, passing_slice, write_waveform_slice)

    def act_compare() -> list[str]:
        report = compare_waveforms(failing_slice, passing_slice)
        return write(report, comparison, write_comparison_report)

    def act_discover() -> list[str]:
        report = discover_repository(repository_root, discovery_config)
        return write(report, repository_map, write_repository_map)

    def act_map() -> list[str]:
        report = map_signals_to_source(repository_map, comparison_path=comparison)
        return write(report, signal_map, write_signal_source_map)

    def act_trace() -> list[str]:
        report = trace_drivers(signal_map, repository_map)
        return write(report, driver_trace, write_driver_trace)

    def act_graph() -> list[str]:
        report = build_failure_divergence_graph(comparison, signal_map, driver_trace)
        return write(report, divergence_graph, write_divergence_graph)

    def act_reduce() -> list[str]:
        report = reduce_relevant_signals(failing_slice, reduced_slice)
        write_reduction_report(report, reduction_report)
        return [str(item) for item in report.warnings]

    def act_synthesize() -> list[str]:
        report = synthesize_failure_report(
            divergence_graph,
            reduction_path=reduction_report,
            driver_trace_path=driver_trace,
            verification_strength_path=verification_strength_path,
            review_path=review_path,
        )
        write_failure_report(report, failure_report_json)
        write_failure_markdown(report, failure_report_md)
        return [str(item) for item in report.warnings]

    synth_inputs = [rel(divergence_graph), rel(reduction_report), rel(driver_trace)]
    if verification_strength_path is not None:
        synth_inputs.append(str(verification_strength_path))
    if review_path is not None:
        synth_inputs.append(str(review_path))

    return [
        _Stage(
            "extract-failing",
            [str(failing_vcd)],
            [
                _Output(
                    "failing-slice",
                    "waveform_slice_report",
                    failing_slice,
                    WaveformSliceReport,
                    WAVEFORM_SLICE_SCHEMA_VERSION,
                )
            ],
            act_extract_failing,
        ),
        _Stage(
            "extract-passing",
            [str(passing_vcd)],
            [
                _Output(
                    "passing-slice",
                    "waveform_slice_report",
                    passing_slice,
                    WaveformSliceReport,
                    WAVEFORM_SLICE_SCHEMA_VERSION,
                )
            ],
            act_extract_passing,
        ),
        _Stage(
            "compare-waveforms",
            [rel(failing_slice), rel(passing_slice)],
            [
                _Output(
                    "comparison",
                    "waveform_comparison_report",
                    comparison,
                    WaveformComparisonReport,
                    WAVEFORM_COMPARISON_SCHEMA_VERSION,
                )
            ],
            act_compare,
        ),
        _Stage(
            "inspect-repo",
            [str(repository_root)],
            [
                _Output(
                    "repository-map",
                    "discovery_repository_map",
                    repository_map,
                    RepositoryMap,
                    REPOSITORY_MAP_SCHEMA_VERSION,
                )
            ],
            act_discover,
        ),
        _Stage(
            "map-signals",
            [rel(repository_map), rel(comparison)],
            [
                _Output(
                    "signal-source-map",
                    "signal_source_map_report",
                    signal_map,
                    SignalSourceMapReport,
                    SIGNAL_SOURCE_MAP_SCHEMA_VERSION,
                )
            ],
            act_map,
        ),
        _Stage(
            "trace-drivers",
            [rel(signal_map), rel(repository_map)],
            [
                _Output(
                    "driver-trace",
                    "rtl_driver_trace_report",
                    driver_trace,
                    RtlDriverTraceReport,
                    RTL_DRIVER_TRACE_SCHEMA_VERSION,
                )
            ],
            act_trace,
        ),
        _Stage(
            "divergence-graph",
            [rel(comparison), rel(signal_map), rel(driver_trace)],
            [
                _Output(
                    "divergence-graph",
                    "failure_divergence_graph_report",
                    divergence_graph,
                    FailureDivergenceGraphReport,
                    FAILURE_DIVERGENCE_GRAPH_SCHEMA_VERSION,
                )
            ],
            act_graph,
        ),
        _Stage(
            "reduce-signals",
            [rel(failing_slice)],
            [
                _Output(
                    "reduction",
                    "relevant_signal_reduction_report",
                    reduction_report,
                    RelevantSignalReductionReport,
                    RELEVANT_SIGNAL_REDUCTION_SCHEMA_VERSION,
                ),
                _Output(
                    "reduced-slice",
                    "waveform_slice_report",
                    reduced_slice,
                    WaveformSliceReport,
                    WAVEFORM_SLICE_SCHEMA_VERSION,
                ),
            ],
            act_reduce,
        ),
        _Stage(
            "synthesize-failure-report",
            synth_inputs,
            [
                _Output(
                    "failure-report",
                    "failure_report",
                    failure_report_json,
                    FailureReport,
                    FAILURE_REPORT_SCHEMA_VERSION,
                ),
                _Output(
                    "failure-report-markdown",
                    "failure_report_markdown",
                    failure_report_md,
                    None,
                    None,
                ),
            ],
            act_synthesize,
        ),
    ]


def _validate_reuse(
    run_dir: Path, stage: _Stage, prior_artifacts: dict[str, dict[str, object]]
) -> tuple[bool, str]:
    for output in stage.outputs:
        relative = output.path.relative_to(run_dir).as_posix()
        if not output.path.exists() or not output.path.is_file():
            return False, f"missing artifact {relative}"
        recorded = prior_artifacts.get(relative)
        if recorded is None:
            return False, f"missing provenance for {relative}"
        recorded_hash = recorded.get("sha256")
        if not isinstance(recorded_hash, str):
            return False, f"missing recorded sha256 for {relative}"
        if _sha256(output.path) != recorded_hash:
            return False, f"sha256 mismatch for {relative}"
        if output.model is not None:
            try:
                report = output.model.model_validate_json(output.path.read_text(encoding="utf-8"))
            except (ValidationError, ValueError, OSError):
                return False, f"invalid artifact {relative}"
            version = getattr(report, "schema_version", None)
            if version != output.schema_version:
                return False, f"unsupported schema version for {relative}"
    return True, "ok"


def _collect_artifacts(run_dir: Path, stage: _Stage) -> list[RunArtifact]:
    collected: list[RunArtifact] = []
    for output in stage.outputs:
        relative = output.path.relative_to(run_dir).as_posix()
        collected.append(
            RunArtifact(
                artifact_id=output.artifact_id,
                kind=output.kind,
                relative_path=relative,
                schema_version=_schema_version(output.path),
                sha256=_sha256(output.path),
            )
        )
    return collected


def _invalidate_outputs(stage: _Stage) -> None:
    for output in stage.outputs:
        if output.path.exists():
            output.path.unlink()


def _prior_index(
    prior: dict[str, object] | None,
) -> tuple[dict[str, str], dict[str, dict[str, object]]]:
    dispositions: dict[str, str] = {}
    artifacts: dict[str, dict[str, object]] = {}
    if prior is None:
        return dispositions, artifacts
    stages = prior.get("stages")
    if isinstance(stages, list):
        for entry in stages:
            if isinstance(entry, dict):
                dispositions[str(entry.get("name"))] = str(entry.get("disposition"))
    recorded = prior.get("artifacts")
    if isinstance(recorded, list):
        for entry in recorded:
            if isinstance(entry, dict):
                artifacts[str(entry.get("relative_path"))] = entry
    return dispositions, artifacts


def _load_prior_manifest(run_dir: Path) -> dict[str, object] | None:
    path = run_dir / "run-manifest.json"
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    if (
        raw.get("schema_version")
        != FailureIntelligenceRunManifest.model_fields["schema_version"].default
    ):
        return None
    return raw


def _inputs_match(
    prior: dict[str, object],
    failing_vcd: Path,
    passing_vcd: Path,
    repository_root: Path,
    failure_time: int,
    before: int,
    after: int,
) -> bool:
    return (
        prior.get("failing_vcd") == str(failing_vcd.resolve())
        and prior.get("passing_vcd") == str(passing_vcd.resolve())
        and prior.get("repository_root") == str(repository_root.resolve())
        and prior.get("failure_time") == failure_time
        and prior.get("before") == before
        and prior.get("after") == after
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
