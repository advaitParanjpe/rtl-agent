from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from rtl_agent.failure_divergence_graph_models import FailureDivergenceGraphReport
from rtl_agent.failure_fingerprint_models import (
    FailureFingerprintReport,
    FingerprintArtifactInput,
    FingerprintComparisonReport,
    FingerprintComponent,
    FingerprintComponentComparison,
    FingerprintDigest,
    FingerprintMatchKind,
)
from rtl_agent.failure_intelligence_run_models import FailureIntelligenceRunManifest
from rtl_agent.failure_report_models import FailureReport
from rtl_agent.models import CommandResult
from rtl_agent.relevant_signal_models import RelevantSignalReductionReport
from rtl_agent.rtl_driver_trace_models import RtlDriverTraceReport
from rtl_agent.signal_source_map_models import SignalSourceMapReport
from rtl_agent.triage_models import TriageReport
from rtl_agent.waveform_comparison_models import WaveformComparisonReport


class FailureFingerprintError(RuntimeError):
    pass


_PARSER_NOTES = [
    "Failure fingerprints are deterministic, read-only summaries of observed evidence. "
    "They exclude run IDs, execution timestamps, durations, absolute paths, UUIDs, and hashes.",
    "The fingerprint is not a root-cause claim and uses no new waveform, RTL, or "
    "semantic analysis.",
]


_EXACT_FIELDS = [
    "assertion_identity",
    "terminal_outcome",
    "failure_time_characteristics",
    "earliest_divergent_signals",
    "ranked_divergent_signals",
    "ranked_relevant_signals",
    "transition_xz_characteristics",
    "mapped_sources",
    "driver_dependency_shape",
    "unresolved_markers",
    "ambiguous_markers",
    "graph_shape",
]

_FAMILY_FIELDS = [
    "assertion_identity",
    "terminal_outcome",
    "earliest_divergent_signals",
    "ranked_divergent_signals",
    "ranked_relevant_signals",
    "transition_xz_characteristics",
    "mapped_sources",
    "driver_dependency_shape",
    "unresolved_markers",
    "ambiguous_markers",
    "graph_shape",
]


def fingerprint_run(run_dir: Path) -> FailureFingerprintReport:
    resolved = run_dir.resolve()
    manifest_path = resolved / "run-manifest.json"
    if not manifest_path.exists():
        raise FailureFingerprintError(f"run manifest not found: {manifest_path}")
    try:
        manifest = FailureIntelligenceRunManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError, ValueError) as exc:
        raise FailureFingerprintError(f"run manifest is unreadable: {manifest_path}") from exc

    artifacts = _artifact_index(manifest, resolved)
    warnings: list[str] = []
    inputs: list[FingerprintArtifactInput] = []

    failure_report = _load_optional(
        artifacts.get("failure_report"),
        FailureReport,
        "failure_report",
        resolved,
        inputs,
        warnings,
    )
    comparison = _load_optional(
        artifacts.get("waveform_comparison_report"),
        WaveformComparisonReport,
        "waveform_comparison_report",
        resolved,
        inputs,
        warnings,
    )
    reduction = _load_optional(
        artifacts.get("relevant_signal_reduction_report"),
        RelevantSignalReductionReport,
        "relevant_signal_reduction_report",
        resolved,
        inputs,
        warnings,
    )
    signal_map = _load_optional(
        artifacts.get("signal_source_map_report"),
        SignalSourceMapReport,
        "signal_source_map_report",
        resolved,
        inputs,
        warnings,
    )
    driver_trace = _load_optional(
        artifacts.get("rtl_driver_trace_report"),
        RtlDriverTraceReport,
        "rtl_driver_trace_report",
        resolved,
        inputs,
        warnings,
    )
    graph = _load_optional(
        artifacts.get("failure_divergence_graph_report"),
        FailureDivergenceGraphReport,
        "failure_divergence_graph_report",
        resolved,
        inputs,
        warnings,
    )
    triage = _load_optional(
        artifacts.get("triage_report"),
        TriageReport,
        "triage_report",
        resolved,
        inputs,
        warnings,
    )
    command = _load_optional(
        artifacts.get("command_result"),
        CommandResult,
        "command_result",
        resolved,
        inputs,
        warnings,
    )

    fields = _component_fields(
        failure_report=failure_report,
        comparison=comparison,
        reduction=reduction,
        signal_map=signal_map,
        driver_trace=driver_trace,
        graph=graph,
        triage=triage,
        command=command,
    )
    insufficient = _insufficient_evidence(fields)
    exact_digest = _digest({name: fields[name] for name in _EXACT_FIELDS})
    family_digest = _digest({name: fields[name] for name in _FAMILY_FIELDS})
    components = [
        FingerprintComponent(name=name, values=list(fields[name])) for name in _EXACT_FIELDS
    ]
    return FailureFingerprintReport(
        source_run_dir=None,
        inputs=sorted(inputs, key=lambda item: (item.kind, str(item.path))),
        exact_digest=exact_digest,
        family_digest=family_digest,
        digest=FingerprintDigest(exact=exact_digest, family=family_digest),
        assertion_identity=fields["assertion_identity"],
        terminal_outcome=fields["terminal_outcome"],
        failure_time_characteristics=fields["failure_time_characteristics"],
        earliest_divergent_signals=fields["earliest_divergent_signals"],
        ranked_divergent_signals=fields["ranked_divergent_signals"],
        ranked_relevant_signals=fields["ranked_relevant_signals"],
        transition_xz_characteristics=fields["transition_xz_characteristics"],
        mapped_sources=fields["mapped_sources"],
        driver_dependency_shape=fields["driver_dependency_shape"],
        unresolved_markers=fields["unresolved_markers"],
        ambiguous_markers=fields["ambiguous_markers"],
        graph_shape=fields["graph_shape"],
        components=components,
        insufficient_evidence=insufficient,
        warnings=sorted(dict.fromkeys(warnings)),
        parser_notes=_PARSER_NOTES,
    )


def compare_fingerprints(left_path: Path, right_path: Path) -> FingerprintComparisonReport:
    left = _load_fingerprint(left_path)
    right = _load_fingerprint(right_path)
    component_matches = [
        FingerprintComponentComparison(
            component=name,
            match=getattr(left, name) == getattr(right, name),
            left=list(getattr(left, name)),
            right=list(getattr(right, name)),
        )
        for name in _EXACT_FIELDS
    ]
    exact_match = left.exact_digest == right.exact_digest
    family_match = left.family_digest == right.family_digest
    if left.insufficient_evidence or right.insufficient_evidence:
        kind = FingerprintMatchKind.INSUFFICIENT
    elif exact_match:
        kind = FingerprintMatchKind.EXACT
    elif family_match:
        kind = FingerprintMatchKind.SAME_FAMILY
    else:
        shared = sum(1 for item in component_matches if item.match)
        kind = (
            FingerprintMatchKind.RELATED_DIFFERENT
            if shared > 0
            else FingerprintMatchKind.INSUFFICIENT
        )
    return FingerprintComparisonReport(
        left_path=left_path.resolve(),
        right_path=right_path.resolve(),
        match_kind=kind,
        exact_match=exact_match,
        family_match=family_match,
        component_matches=component_matches,
        summary=_comparison_summary(kind, component_matches),
        warnings=sorted(dict.fromkeys(left.warnings + right.warnings)),
        parser_notes=_PARSER_NOTES,
    )


def write_fingerprint_report(report: FailureFingerprintReport, output: Path) -> None:
    if output.exists() and output.is_dir():
        raise FailureFingerprintError(f"output path is a directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_json(report.model_dump(mode="json")), encoding="utf-8")


def write_fingerprint_comparison(report: FingerprintComparisonReport, output: Path) -> None:
    if output.exists() and output.is_dir():
        raise FailureFingerprintError(f"output path is a directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_json(report.model_dump(mode="json")), encoding="utf-8")


def _artifact_index(manifest: FailureIntelligenceRunManifest, run_dir: Path) -> dict[str, Path]:
    by_kind: dict[str, Path] = {}
    for artifact in manifest.artifacts:
        if artifact.path_kind != "run_relative":
            continue
        path = _resolve_run_relative(run_dir, artifact.relative_path)
        by_kind.setdefault(artifact.kind, path)
    if manifest.failure_report_path:
        by_kind.setdefault(
            "failure_report", _resolve_run_relative(run_dir, manifest.failure_report_path)
        )
    return by_kind


def _resolve_run_relative(run_dir: Path, relative_path: str) -> Path:
    path = (run_dir / relative_path).resolve()
    try:
        path.relative_to(run_dir.resolve())
    except ValueError as exc:
        raise FailureFingerprintError(f"unsafe run-relative path: {relative_path}") from exc
    return path


def _load_optional(
    path: Path | None,
    model: type[Any],
    kind: str,
    run_dir: Path,
    inputs: list[FingerprintArtifactInput],
    warnings: list[str],
) -> Any | None:
    if path is None:
        warnings.append(f"artifact unavailable for fingerprint: {kind}")
        return None
    if not path.exists():
        warnings.append(f"artifact missing for fingerprint: {kind}")
        return None
    try:
        loaded = model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise FailureFingerprintError(f"could not load {kind}: {path}") from exc
    schema_version = getattr(loaded, "schema_version", None)
    inputs.append(
        FingerprintArtifactInput(
            kind=kind,
            path=path.resolve().relative_to(run_dir),
            schema_version=schema_version if isinstance(schema_version, int) else None,
        )
    )
    return loaded


def _component_fields(
    *,
    failure_report: FailureReport | None,
    comparison: WaveformComparisonReport | None,
    reduction: RelevantSignalReductionReport | None,
    signal_map: SignalSourceMapReport | None,
    driver_trace: RtlDriverTraceReport | None,
    graph: FailureDivergenceGraphReport | None,
    triage: TriageReport | None,
    command: CommandResult | None,
) -> dict[str, list[str]]:
    earliest = []
    if failure_report and failure_report.earliest_divergence_signals:
        earliest = list(failure_report.earliest_divergence_signals)
    elif comparison:
        earliest = list(comparison.global_earliest_divergence_signals)

    ranked_divergent = []
    if failure_report and failure_report.observed_failure_facts:
        ranked_divergent = [
            _join(
                fact.identifier,
                _value(fact.signal),
                _value(fact.failing_value),
                _value(fact.passing_value),
                str(fact.xz_difference),
            )
            for fact in failure_report.observed_failure_facts
        ]
    elif comparison:
        ranked_divergent = [
            _join(
                signal.name,
                _value(signal.failing_value_at_divergence),
                _value(signal.passing_value_at_divergence),
                str(signal.xz_difference),
            )
            for signal in sorted(
                comparison.diverging_signals,
                key=lambda item: (-item.divergence_score, item.name),
            )
        ]

    return {
        "assertion_identity": _assertion_identity(triage, reduction),
        "terminal_outcome": _terminal_outcome(command, triage),
        "failure_time_characteristics": _time_characteristics(
            failure_report, comparison, reduction
        ),
        "earliest_divergent_signals": sorted(earliest),
        "ranked_divergent_signals": ranked_divergent,
        "ranked_relevant_signals": _ranked_relevant(failure_report, reduction),
        "transition_xz_characteristics": _transition_xz(comparison, failure_report),
        "mapped_sources": _mapped_sources(failure_report, signal_map, graph),
        "driver_dependency_shape": _driver_shape(failure_report, driver_trace, graph),
        "unresolved_markers": _unresolved_markers(failure_report, driver_trace, graph),
        "ambiguous_markers": _ambiguous_markers(failure_report, signal_map, graph),
        "graph_shape": _graph_shape(graph),
    }


def _assertion_identity(
    triage: TriageReport | None, reduction: RelevantSignalReductionReport | None
) -> list[str]:
    values: list[str] = []
    if triage:
        for item in triage.assertion_failures:
            values.append(_join(_value(item.signal_or_label), item.summary))
    if reduction and (reduction.assertion_signal or reduction.assertion_summary):
        values.append(
            _join(_value(reduction.assertion_signal), _value(reduction.assertion_summary))
        )
    return sorted(dict.fromkeys(values))


def _terminal_outcome(command: CommandResult | None, triage: TriageReport | None) -> list[str]:
    if command:
        return [_join(command.command_name, str(command.status), _value(command.exit_code))]
    if triage:
        return [_join(triage.command_name, triage.command_status, _value(triage.command_exit_code))]
    return []


def _time_characteristics(
    failure_report: FailureReport | None,
    comparison: WaveformComparisonReport | None,
    reduction: RelevantSignalReductionReport | None,
) -> list[str]:
    values: list[str] = []
    if failure_report and failure_report.earliest_divergence_time is not None:
        values.append(f"earliest={failure_report.earliest_divergence_time}")
    if comparison:
        values.append(
            _join(
                "basis",
                str(comparison.time_basis.kind),
                str(comparison.time_basis.normalized),
                comparison.time_basis.common_end - comparison.time_basis.common_start,
                _value(comparison.global_earliest_divergence_time),
            )
        )
    if reduction:
        values.append(f"reduction_failure_time={reduction.failure_time}")
    return sorted(dict.fromkeys(values))


def _ranked_relevant(
    failure_report: FailureReport | None, reduction: RelevantSignalReductionReport | None
) -> list[str]:
    if failure_report and failure_report.ranked_relevant_signals:
        return [
            _join(item.name, item.score, ",".join(sorted(item.criteria)))
            for item in failure_report.ranked_relevant_signals
        ]
    if reduction:
        return [
            _join(
                item.name,
                item.identifier,
                item.score,
                item.transition_count,
                _value(item.nearest_transition_distance),
                ",".join(sorted(str(reason.criterion) for reason in item.reasons)),
            )
            for item in reduction.retained_signals
        ]
    return []


def _transition_xz(
    comparison: WaveformComparisonReport | None, failure_report: FailureReport | None
) -> list[str]:
    if comparison:
        return [
            _join(
                item.name,
                item.failing_transition_count,
                item.passing_transition_count,
                str(item.xz_difference),
                item.divergence_duration,
            )
            for item in sorted(comparison.diverging_signals, key=lambda signal: signal.name)
        ]
    if failure_report:
        return [
            _join(item.identifier, str(item.xz_difference), item.divergence_score)
            for item in failure_report.observed_failure_facts
        ]
    return []


def _mapped_sources(
    failure_report: FailureReport | None,
    signal_map: SignalSourceMapReport | None,
    graph: FailureDivergenceGraphReport | None,
) -> list[str]:
    values: list[str] = []
    if failure_report:
        values.extend(
            _join(
                item.identifier,
                item.declaration_name,
                item.declaration_kind,
                item.file_path,
                _value(item.mapping_status),
            )
            for item in failure_report.candidate_source_locations
        )
    if signal_map:
        for mapping in signal_map.mappings:
            for candidate in mapping.candidates:
                values.append(
                    _join(
                        mapping.leaf,
                        mapping.status,
                        candidate.declaration_name,
                        candidate.declaration_kind,
                        candidate.file_path,
                        str(candidate.primary),
                    )
                )
    if graph:
        for node in graph.nodes:
            for declaration in node.declarations:
                values.append(
                    _join(
                        node.identifier,
                        _value(node.mapping_status),
                        declaration.declaration_name,
                        declaration.declaration_kind,
                        declaration.file_path,
                    )
                )
    return sorted(dict.fromkeys(values))


def _driver_shape(
    failure_report: FailureReport | None,
    driver_trace: RtlDriverTraceReport | None,
    graph: FailureDivergenceGraphReport | None,
) -> list[str]:
    values: list[str] = []
    if failure_report:
        values.extend(
            _join(
                item.source_signal,
                item.depends_on,
                item.label,
                item.statement_kind,
                item.evidence_file,
                _normalize_statement(item.statement_text),
                _normalize_statement(item.guard),
            )
            for item in failure_report.driver_dependency_evidence
        )
    if driver_trace:
        for edge in driver_trace.dependency_edges:
            values.append(
                _join(
                    edge.source_signal,
                    edge.depends_on,
                    edge.label,
                    edge.statement_kind,
                    edge.evidence_file,
                )
            )
    if graph:
        values.extend(
            _join(edge.source, edge.target, edge.label, edge.statement_kind, edge.evidence_file)
            for edge in graph.edges
        )
    return sorted(dict.fromkeys(values))


def _unresolved_markers(
    failure_report: FailureReport | None,
    driver_trace: RtlDriverTraceReport | None,
    graph: FailureDivergenceGraphReport | None,
) -> list[str]:
    values: list[str] = []
    if failure_report:
        values.extend(
            _join(item.identifier, item.kind, item.detail)
            for item in failure_report.unresolved_evidence
        )
    if driver_trace:
        values.extend(driver_trace.unresolved_identifiers)
    if graph:
        values.extend(graph.unresolved_identifiers)
    return sorted(dict.fromkeys(values))


def _ambiguous_markers(
    failure_report: FailureReport | None,
    signal_map: SignalSourceMapReport | None,
    graph: FailureDivergenceGraphReport | None,
) -> list[str]:
    values: list[str] = []
    if failure_report:
        values.extend(
            _join(item.identifier, item.kind, item.detail)
            for item in failure_report.ambiguous_evidence
        )
    if signal_map:
        values.extend(
            mapping.leaf for mapping in signal_map.mappings if mapping.status == "ambiguous"
        )
    if graph:
        values.extend(node.identifier for node in graph.nodes if node.mapping_status == "ambiguous")
    return sorted(dict.fromkeys(values))


def _graph_shape(graph: FailureDivergenceGraphReport | None) -> list[str]:
    if graph is None:
        return []
    values = [
        _join(
            "node",
            node.identifier,
            node.depth,
            str(node.is_root),
            _value(node.mapping_status),
            _value(node.driver_resolved),
            _value(node.driver_count),
        )
        for node in graph.nodes
    ]
    values.extend(
        _join("edge", edge.source, edge.target, edge.label, edge.statement_kind, edge.evidence_file)
        for edge in graph.edges
    )
    values.append(_join("roots", ",".join(sorted(graph.root_identifiers))))
    return sorted(values)


def _insufficient_evidence(fields: dict[str, list[str]]) -> list[str]:
    reasons: list[str] = []
    if not fields["earliest_divergent_signals"]:
        reasons.append("missing earliest divergent signal evidence")
    if not fields["mapped_sources"]:
        reasons.append("missing mapped source evidence")
    if not fields["driver_dependency_shape"] and not fields["graph_shape"]:
        reasons.append("missing driver/dependency graph evidence")
    return reasons


def _digest(payload: dict[str, list[str]]) -> str:
    return sha256(_json(payload).encode("utf-8")).hexdigest()


def _load_fingerprint(path: Path) -> FailureFingerprintReport:
    try:
        return FailureFingerprintReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise FailureFingerprintError(f"could not load fingerprint: {path}") from exc


def _comparison_summary(
    kind: FingerprintMatchKind, components: list[FingerprintComponentComparison]
) -> str:
    matched = sorted(item.component for item in components if item.match)
    differed = sorted(item.component for item in components if not item.match)
    return (
        f"{kind}: matched {len(matched)} component(s)"
        + (f" ({', '.join(matched)})" if matched else "")
        + "; differed "
        + str(len(differed))
        + (" component(s): " + ", ".join(differed) if differed else " component(s)")
    )


def _normalize_time(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.strip().lower().split())


def _normalize_statement(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.strip().split())


def _join(*parts: object) -> str:
    return "|".join(_value(part) for part in parts)


def _value(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _json(data: object) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"
