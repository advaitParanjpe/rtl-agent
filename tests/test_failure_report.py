from __future__ import annotations

import json
from pathlib import Path

import pytest

from rtl_agent.failure_divergence_graph_models import (
    FailureDivergenceGraphReport,
    GraphEdge,
    GraphNode,
    NodeDeclaration,
    NodeDivergence,
)
from rtl_agent.failure_report import (
    FailureReportError,
    render_failure_markdown,
    synthesize_failure_report,
    write_failure_report,
)
from rtl_agent.relevant_signal_models import (
    RankedSignal,
    RelevantSignalReductionReport,
    SignalRelevanceCriterion,
    SignalRelevanceReason,
)
from rtl_agent.review_models import (
    EvidenceCitation,
    ReviewFinding,
    ReviewFindingSeverity,
    ReviewFindingSource,
    ReviewOutcome,
    ReviewReport,
)
from rtl_agent.rtl_driver_trace_models import (
    DriverStatement,
    EvidenceLabel,
    RtlDriverTraceReport,
    StatementKind,
    TracedSignal,
    TraceStatus,
)
from rtl_agent.verification_strength_models import (
    VerificationStrengthLevel,
    VerificationStrengthReport,
    WeakPatternSeverity,
    WeakValidationPattern,
)


def make_graph(
    tmp_path: Path,
    *,
    roots: list[tuple[str, str, int]],
    edges: list[tuple[str, str, int]] | None = None,
    unresolved: list[str] | None = None,
    ambiguous: list[str] | None = None,
    earliest: int | None = None,
    name: str = "graph.json",
) -> Path:
    nodes: list[GraphNode] = []
    for identifier, signal, first_time in roots:
        nodes.append(
            GraphNode(
                identifier=identifier,
                depth=0,
                is_root=True,
                signal=signal,
                mapping_status="exact",
                driver_resolved=False,
                driver_count=0,
                divergence=NodeDivergence(
                    first_divergence_time=first_time,
                    failing_value="x",
                    passing_value="0",
                    divergence_score=100,
                    xz_difference=True,
                ),
                declarations=[
                    NodeDeclaration(
                        declaration_name="top",
                        declaration_kind="module",
                        file_path="rtl/top.sv",
                        line=1,
                    )
                ],
            )
        )
    for identifier in ambiguous or []:
        nodes.append(
            GraphNode(identifier=identifier, depth=1, is_root=False, mapping_status="ambiguous")
        )
    graph = FailureDivergenceGraphReport(
        comparison_path=tmp_path / "cmp.json",
        signal_source_map_path=tmp_path / "map.json",
        driver_trace_path=tmp_path / "trace.json",
        max_depth=3,
        max_nodes=128,
        root_identifiers=sorted(identifier for identifier, _, _ in roots),
        global_earliest_divergence_time=earliest,
        nodes=nodes,
        edges=[
            GraphEdge(
                source=src,
                target=dst,
                label=EvidenceLabel.TEXTUAL,
                statement_kind=StatementKind.CONTINUOUS_ASSIGN,
                evidence_file="rtl/top.sv",
                evidence_line=line,
            )
            for src, dst, line in (edges or [])
        ],
        unresolved_identifiers=unresolved or [],
    )
    path = tmp_path / name
    path.write_text(json.dumps(graph.model_dump(mode="json")), encoding="utf-8")
    return path


def make_reduction(tmp_path: Path) -> Path:
    report = RelevantSignalReductionReport(
        waveform_slice_path=tmp_path / "slice.json",
        failure_time=40,
        max_signals=32,
        total_candidate_signals=2,
        reduced_slice_path=tmp_path / "reduced.json",
        reduced_slice_sha256="0" * 64,
        retained_signals=[
            RankedSignal(
                name="top.dut.valid",
                identifier="valid",
                score=145,
                transition_count=1,
                reasons=[
                    SignalRelevanceReason(
                        criterion=SignalRelevanceCriterion.ASSERTION_NAMED,
                        points=100,
                        detail="named",
                    )
                ],
            )
        ],
    )
    path = tmp_path / "reduction.json"
    path.write_text(json.dumps(report.model_dump(mode="json")), encoding="utf-8")
    return path


def make_driver_trace(tmp_path: Path) -> Path:
    report = RtlDriverTraceReport(
        signal_source_map_path=tmp_path / "map.json",
        repository_map_path=tmp_path / "repo.json",
        repository_root=tmp_path / "repo",
        max_depth=2,
        max_nodes=64,
        traced_signals=[
            TracedSignal(
                signal="top.q",
                leaf="q",
                status=TraceStatus.TRACED,
                mapping_status="exact",
                drivers=[
                    DriverStatement(
                        file_path="rtl/top.sv",
                        line=3,
                        kind=StatementKind.CONTINUOUS_ASSIGN,
                        label=EvidenceLabel.TEXTUAL,
                        statement_text="assign q = a & b;",
                        lhs_identifiers=["q"],
                        rhs_identifiers=["a", "b"],
                        guard="if (en)",
                    )
                ],
            )
        ],
    )
    path = tmp_path / "trace.json"
    path.write_text(json.dumps(report.model_dump(mode="json")), encoding="utf-8")
    return path


def make_verification(tmp_path: Path) -> Path:
    report = VerificationStrengthReport(
        strength=VerificationStrengthLevel.INSUFFICIENT,
        score=0,
        task_contract_path=tmp_path / "tc.json",
        repository_map_path=tmp_path / "repo.json",
        implementation_report_path=tmp_path / "impl.json",
        weak_patterns=[
            WeakValidationPattern(
                pattern_id="no-validation",
                severity=WeakPatternSeverity.ERROR,
                title="No validation",
                description="none",
                evidence=[EvidenceCitation(artifact=tmp_path / "impl.json", detail="x")],
            )
        ],
        summary="insufficient",
    )
    path = tmp_path / "vs.json"
    path.write_text(json.dumps(report.model_dump(mode="json")), encoding="utf-8")
    return path


def make_review(tmp_path: Path) -> Path:
    report = ReviewReport(
        outcome=ReviewOutcome.UNACCEPTABLE,
        task_contract_path=tmp_path / "tc.json",
        repository_map_path=tmp_path / "repo.json",
        implementation_report_path=tmp_path / "impl.json",
        deterministic_findings=[
            ReviewFinding(
                finding_id="det-validation-missing",
                source=ReviewFindingSource.DETERMINISTIC,
                severity=ReviewFindingSeverity.ERROR,
                title="Validation missing",
                description="none",
                evidence=[EvidenceCitation(artifact=tmp_path / "impl.json", detail="x")],
            )
        ],
        summary="unacceptable",
    )
    path = tmp_path / "review.json"
    path.write_text(json.dumps(report.model_dump(mode="json")), encoding="utf-8")
    return path


def test_observed_facts_and_earliest(tmp_path: Path) -> None:
    graph = make_graph(
        tmp_path,
        roots=[("state", "top.dut.state", 25), ("valid", "top.dut.valid", 25)],
        earliest=25,
    )

    report = synthesize_failure_report(graph)

    assert [fact.identifier for fact in report.observed_failure_facts] == ["state", "valid"]
    assert all(fact.source == "divergence-graph" for fact in report.observed_failure_facts)
    assert report.earliest_divergence_time == 25
    assert report.earliest_divergence_signals == ["state", "valid"]


def test_source_locations_carry_mapping_status(tmp_path: Path) -> None:
    graph = make_graph(tmp_path, roots=[("valid", "top.dut.valid", 30)], earliest=30)

    report = synthesize_failure_report(graph)

    assert len(report.candidate_source_locations) == 1
    location = report.candidate_source_locations[0]
    assert location.file_path == "rtl/top.sv"
    assert location.mapping_status == "exact"
    assert location.source == "divergence-graph"


def test_driver_evidence_enriched_from_trace(tmp_path: Path) -> None:
    graph = make_graph(
        tmp_path, roots=[("q", "top.q", 10)], edges=[("q", "a", 3), ("q", "b", 3)], earliest=10
    )
    trace = make_driver_trace(tmp_path)

    report = synthesize_failure_report(graph, driver_trace_path=trace)

    assert len(report.driver_dependency_evidence) == 2
    by_target = {e.depends_on: e for e in report.driver_dependency_evidence}
    assert by_target["a"].statement_text == "assign q = a & b;"
    assert by_target["a"].guard == "if (en)"
    assert by_target["a"].label == "textual"


def test_unresolved_and_ambiguous_evidence(tmp_path: Path) -> None:
    graph = make_graph(
        tmp_path,
        roots=[("valid", "top.dut.valid", 25)],
        unresolved=["valid", "a"],
        ambiguous=["core"],
        earliest=25,
    )

    report = synthesize_failure_report(graph)

    assert {gap.identifier for gap in report.unresolved_evidence} == {"valid", "a"}
    assert all(gap.kind == "unresolved" for gap in report.unresolved_evidence)
    assert {gap.identifier for gap in report.ambiguous_evidence} == {"core"}
    assert all(gap.kind == "ambiguous" for gap in report.ambiguous_evidence)


def test_ranked_signals_and_status_when_supplied(tmp_path: Path) -> None:
    graph = make_graph(tmp_path, roots=[("valid", "top.dut.valid", 25)], earliest=25)

    report = synthesize_failure_report(
        graph,
        reduction_path=make_reduction(tmp_path),
        verification_strength_path=make_verification(tmp_path),
        review_path=make_review(tmp_path),
    )

    assert [s.name for s in report.ranked_relevant_signals] == ["top.dut.valid"]
    assert report.ranked_relevant_signals[0].criteria == ["assertion_named"]
    assert report.verification_status is not None
    assert report.verification_status.strength == "insufficient"
    assert report.verification_status.weak_patterns == ["no-validation"]
    assert report.review_status is not None
    assert report.review_status.outcome == "unacceptable"
    assert report.review_status.error_finding_ids == ["det-validation-missing"]


def test_provenance_includes_referenced_artifacts(tmp_path: Path) -> None:
    graph = make_graph(tmp_path, roots=[("valid", "top.dut.valid", 25)], earliest=25)

    report = synthesize_failure_report(graph)

    ids = {reference.artifact_id for reference in report.generated_from}
    assert {"divergence-graph", "comparison", "signal-source-map", "driver-trace"} <= ids
    graph_ref = next(r for r in report.generated_from if r.artifact_id == "divergence-graph")
    assert graph_ref.sha256 is not None
    assert graph_ref.schema_version == 1


def test_markdown_has_sections_and_never_claims_root_cause(tmp_path: Path) -> None:
    graph = make_graph(tmp_path, roots=[("valid", "top.dut.valid", 25)], earliest=25)
    report = synthesize_failure_report(graph, reduction_path=make_reduction(tmp_path))

    markdown = render_failure_markdown(report)

    assert "## Observed Failure Facts" in markdown
    assert "## Artifact Provenance" in markdown
    assert "never identifies a root cause" in markdown
    # The phrase only appears in the disclaimer, never to label a signal.
    assert markdown.count("root cause") == 1


def test_empty_graph_has_no_facts(tmp_path: Path) -> None:
    graph = make_graph(tmp_path, roots=[])

    report = synthesize_failure_report(graph)

    assert report.observed_failure_facts == []
    assert report.earliest_divergence_time is None


def test_deterministic_output(tmp_path: Path) -> None:
    graph = make_graph(
        tmp_path,
        roots=[("state", "top.dut.state", 25), ("valid", "top.dut.valid", 25)],
        earliest=25,
    )
    report = synthesize_failure_report(graph, reduction_path=make_reduction(tmp_path))

    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_failure_report(report, first)
    write_failure_report(report, second)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    assert json.loads(first.read_text(encoding="utf-8"))["schema_version"] == 1


def test_rejects_malformed_graph(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")

    with pytest.raises(FailureReportError, match="could not load failure-divergence-graph"):
        synthesize_failure_report(bad)
