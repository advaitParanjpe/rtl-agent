from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ValidationError

from rtl_agent.failure_divergence_graph_models import FailureDivergenceGraphReport
from rtl_agent.failure_report_models import (
    ArtifactReference,
    DivergingSignalFact,
    DriverEvidence,
    EvidenceGap,
    FailureReport,
    RankedRelevantSignal,
    ReviewStatus,
    SourceLocation,
    VerificationStatus,
)
from rtl_agent.relevant_signal_models import RelevantSignalReductionReport
from rtl_agent.review_models import ReviewReport
from rtl_agent.rtl_driver_trace_models import RtlDriverTraceReport
from rtl_agent.verification_strength_models import VerificationStrengthReport

_NEVER_ROOT_CAUSE = (
    "This report is a compositional, evidence-cited summary of observed artifacts; it never "
    "identifies a root cause and performs no new waveform, dependency, or semantic analysis."
)


class FailureReportError(RuntimeError):
    pass


def synthesize_failure_report(
    divergence_graph_path: Path,
    *,
    reduction_path: Path | None = None,
    driver_trace_path: Path | None = None,
    verification_strength_path: Path | None = None,
    review_path: Path | None = None,
) -> FailureReport:
    graph = _load(divergence_graph_path, FailureDivergenceGraphReport, "failure-divergence-graph")
    warnings: list[str] = list(graph.warnings)

    references: list[ArtifactReference] = [
        _reference("divergence-graph", "failure_divergence_graph_report", divergence_graph_path),
    ]

    root_nodes = [node for node in graph.nodes if node.is_root]
    facts = [
        DivergingSignalFact(
            signal=node.signal,
            identifier=node.identifier,
            first_divergence_time=node.divergence.first_divergence_time,
            failing_value=node.divergence.failing_value,
            passing_value=node.divergence.passing_value,
            xz_difference=node.divergence.xz_difference,
            divergence_score=node.divergence.divergence_score,
            source="divergence-graph",
        )
        for node in root_nodes
        if node.divergence is not None
    ]
    facts.sort(
        key=lambda item: (
            item.first_divergence_time is None,
            item.first_divergence_time,
            item.identifier,
        )
    )

    earliest = graph.global_earliest_divergence_time
    earliest_signals = sorted(
        fact.identifier for fact in facts if fact.first_divergence_time == earliest
    )

    source_locations: list[SourceLocation] = []
    for node in graph.nodes:
        for declaration in node.declarations:
            source_locations.append(
                SourceLocation(
                    identifier=node.identifier,
                    declaration_name=declaration.declaration_name,
                    declaration_kind=declaration.declaration_kind,
                    file_path=declaration.file_path,
                    line=declaration.line,
                    mapping_status=node.mapping_status,
                    source="divergence-graph",
                )
            )
    source_locations = _dedupe_source_locations(source_locations)

    statement_index = _driver_statement_index(driver_trace_path, references, warnings)
    driver_evidence = [
        DriverEvidence(
            source_signal=edge.source,
            depends_on=edge.target,
            label=edge.label,
            statement_kind=edge.statement_kind,
            evidence_file=edge.evidence_file,
            evidence_line=edge.evidence_line,
            statement_text=statement_index.get(
                (edge.evidence_file, edge.evidence_line), (None, None)
            )[0],
            guard=statement_index.get((edge.evidence_file, edge.evidence_line), (None, None))[1],
            source="divergence-graph",
        )
        for edge in graph.edges
    ]

    unresolved = [
        EvidenceGap(
            identifier=identifier,
            kind="unresolved",
            detail="no driver was resolved for this identifier in the driver trace",
            source="divergence-graph",
        )
        for identifier in graph.unresolved_identifiers
    ]
    ambiguous = [
        EvidenceGap(
            identifier=node.identifier,
            kind="ambiguous",
            detail="signal-source mapping matched multiple candidate declarations",
            source="divergence-graph",
        )
        for node in graph.nodes
        if node.mapping_status == "ambiguous"
    ]

    ranked = _ranked_relevant_signals(reduction_path, references, warnings)
    verification_status = _verification_status(verification_strength_path, references, warnings)
    review_status = _review_status(review_path, references, warnings)

    references.extend(_graph_referenced_artifacts(graph, references))

    return FailureReport(
        divergence_graph_path=divergence_graph_path.resolve(),
        observed_failure_facts=facts,
        earliest_divergence_time=earliest,
        earliest_divergence_signals=earliest_signals,
        ranked_relevant_signals=ranked,
        candidate_source_locations=source_locations,
        driver_dependency_evidence=driver_evidence,
        unresolved_evidence=unresolved,
        ambiguous_evidence=ambiguous,
        verification_status=verification_status,
        review_status=review_status,
        generated_from=references,
        warnings=sorted(dict.fromkeys(warnings)),
        parser_notes=[
            _NEVER_ROOT_CAUSE,
            "Every fact cites the artifact it was composed from; upstream artifacts are listed "
            "under generated_from with their provenance.",
        ],
    )


def write_failure_report(report: FailureReport, output: Path) -> None:
    if output.exists() and output.is_dir():
        raise FailureReportError(f"output path is a directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_failure_markdown(report: FailureReport, output: Path) -> None:
    if output.exists() and output.is_dir():
        raise FailureReportError(f"output path is a directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_failure_markdown(report), encoding="utf-8")


def render_failure_markdown(report: FailureReport) -> str:
    lines: list[str] = ["# Failure Report", "", f"_{_NEVER_ROOT_CAUSE}_", ""]

    lines.append("## Observed Failure Facts")
    if report.observed_failure_facts:
        for fact in report.observed_failure_facts:
            name = fact.signal or fact.identifier
            xz = ", x/z difference" if fact.xz_difference else ""
            lines.append(
                f"- `{name}` diverges at t={fact.first_divergence_time}: "
                f"failing `{fact.failing_value}` vs passing `{fact.passing_value}` "
                f"(score {fact.divergence_score}{xz}) — {fact.source}"
            )
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Earliest Waveform Divergence")
    if report.earliest_divergence_time is not None:
        signals = ", ".join(report.earliest_divergence_signals) or "n/a"
        lines.append(
            f"- earliest divergence at t={report.earliest_divergence_time} for: {signals} "
            "— divergence-graph"
        )
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Ranked Relevant Signals")
    if report.ranked_relevant_signals:
        for index, signal in enumerate(report.ranked_relevant_signals, start=1):
            criteria = ", ".join(signal.criteria) or "n/a"
            lines.append(
                f"{index}. `{signal.name}` (score {signal.score}: {criteria}) — {signal.source}"
            )
    else:
        lines.append("- none supplied")
    lines.append("")

    lines.append("## Candidate RTL Source Locations")
    if report.candidate_source_locations:
        for location in report.candidate_source_locations:
            status = f", mapping: {location.mapping_status}" if location.mapping_status else ""
            lines.append(
                f"- `{location.identifier}` → {location.declaration_kind} "
                f"`{location.declaration_name}` at {location.file_path}:{location.line}"
                f"{status} — {location.source}"
            )
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Textual Driver / Dependency Evidence")
    if report.driver_dependency_evidence:
        for evidence in report.driver_dependency_evidence:
            text = f" — `{evidence.statement_text}`" if evidence.statement_text else ""
            lines.append(
                f"- `{evidence.source_signal}` depends on `{evidence.depends_on}` "
                f"[{evidence.label}, {evidence.statement_kind}] at "
                f"{evidence.evidence_file}:{evidence.evidence_line}{text} — {evidence.source}"
            )
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Unresolved and Ambiguous Evidence")
    unresolved = ", ".join(gap.identifier for gap in report.unresolved_evidence) or "none"
    ambiguous = ", ".join(gap.identifier for gap in report.ambiguous_evidence) or "none"
    lines.append(f"- unresolved: {unresolved} — divergence-graph")
    lines.append(f"- ambiguous: {ambiguous} — divergence-graph")
    lines.append("")

    lines.append("## Verification & Review Status")
    if report.verification_status is not None:
        patterns = ", ".join(report.verification_status.weak_patterns) or "none"
        lines.append(
            f"- verification strength: {report.verification_status.strength} "
            f"(score {report.verification_status.score}); weak patterns: {patterns} "
            f"— {report.verification_status.source}"
        )
    if report.review_status is not None:
        findings = ", ".join(report.review_status.error_finding_ids) or "none"
        lines.append(
            f"- review outcome: {report.review_status.outcome}; error findings: {findings} "
            f"— {report.review_status.source}"
        )
    if report.verification_status is None and report.review_status is None:
        lines.append("- not supplied")
    lines.append("")

    lines.append("## Artifact Provenance")
    for reference in report.generated_from:
        version = (
            f"schema v{reference.schema_version}" if reference.schema_version else "schema n/a"
        )
        digest = f"sha256 {reference.sha256[:12]}…" if reference.sha256 else "sha256 n/a"
        lines.append(
            f"- {reference.artifact_id} ({reference.kind}): {reference.path} [{version}, {digest}]"
        )
    lines.append("")

    return "\n".join(lines)


def _driver_statement_index(
    driver_trace_path: Path | None, references: list[ArtifactReference], warnings: list[str]
) -> dict[tuple[str, int], tuple[str | None, str | None]]:
    if driver_trace_path is None:
        return {}
    trace = _load(driver_trace_path, RtlDriverTraceReport, "driver-trace")
    references.append(_reference("driver-trace", "rtl_driver_trace_report", driver_trace_path))
    index: dict[tuple[str, int], tuple[str | None, str | None]] = {}
    for traced in trace.traced_signals:
        for driver in traced.drivers:
            index.setdefault((driver.file_path, driver.line), (driver.statement_text, driver.guard))
    return index


def _ranked_relevant_signals(
    reduction_path: Path | None, references: list[ArtifactReference], warnings: list[str]
) -> list[RankedRelevantSignal]:
    if reduction_path is None:
        return []
    reduction = _load(reduction_path, RelevantSignalReductionReport, "relevant-signal reduction")
    references.append(_reference("reduction", "relevant_signal_reduction_report", reduction_path))
    return [
        RankedRelevantSignal(
            name=signal.name,
            score=signal.score,
            criteria=[reason.criterion for reason in signal.reasons],
            source="reduction",
        )
        for signal in reduction.retained_signals
    ]


def _verification_status(
    verification_strength_path: Path | None,
    references: list[ArtifactReference],
    warnings: list[str],
) -> VerificationStatus | None:
    if verification_strength_path is None:
        return None
    strength = _load(
        verification_strength_path, VerificationStrengthReport, "verification-strength"
    )
    references.append(
        _reference(
            "verification-strength",
            "verification_strength_report",
            verification_strength_path,
        )
    )
    return VerificationStatus(
        strength=str(strength.strength),
        score=strength.score,
        weak_patterns=[pattern.pattern_id for pattern in strength.weak_patterns],
        source="verification-strength",
    )


def _review_status(
    review_path: Path | None, references: list[ArtifactReference], warnings: list[str]
) -> ReviewStatus | None:
    if review_path is None:
        return None
    review = _load(review_path, ReviewReport, "review")
    references.append(_reference("review", "review_report", review_path))
    error_ids = sorted(
        finding.finding_id
        for finding in [*review.deterministic_findings, *review.provider_findings]
        if str(finding.severity) == "error"
    )
    return ReviewStatus(outcome=str(review.outcome), error_finding_ids=error_ids, source="review")


def _graph_referenced_artifacts(
    graph: FailureDivergenceGraphReport, existing: list[ArtifactReference]
) -> list[ArtifactReference]:
    known = {reference.path for reference in existing}
    referenced: list[ArtifactReference] = []
    for artifact_id, kind, path in (
        ("comparison", "waveform_comparison_report", graph.comparison_path),
        ("signal-source-map", "signal_source_map_report", graph.signal_source_map_path),
        ("driver-trace", "rtl_driver_trace_report", graph.driver_trace_path),
    ):
        if path.resolve() in known:
            continue
        known.add(path.resolve())
        referenced.append(_reference(artifact_id, kind, path))
    return referenced


def _dedupe_source_locations(locations: list[SourceLocation]) -> list[SourceLocation]:
    seen: set[tuple[str, str, int]] = set()
    result: list[SourceLocation] = []
    for location in sorted(
        locations, key=lambda item: (item.identifier, item.file_path, item.line)
    ):
        key = (location.identifier, location.file_path, location.line)
        if key not in seen:
            seen.add(key)
            result.append(location)
    return result


def _reference(artifact_id: str, kind: str, path: Path) -> ArtifactReference:
    resolved = path.resolve()
    schema_version: int | None = None
    sha256: str | None = None
    if resolved.exists() and resolved.is_file():
        sha256 = _sha256(resolved)
        schema_version = _schema_version(resolved)
    return ArtifactReference(
        artifact_id=artifact_id,
        kind=kind,
        path=resolved,
        schema_version=schema_version,
        sha256=sha256,
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


def _load[ModelT: BaseModel](path: Path, model: type[ModelT], label: str) -> ModelT:
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise FailureReportError(f"could not load {label} report: {path}") from exc
