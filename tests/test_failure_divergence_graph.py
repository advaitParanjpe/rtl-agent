from __future__ import annotations

import json
from pathlib import Path

import pytest

from rtl_agent.failure_divergence_graph import (
    FailureDivergenceGraphError,
    build_failure_divergence_graph,
    write_divergence_graph,
)
from rtl_agent.rtl_driver_trace_models import (
    DependencyEdge,
    EvidenceLabel,
    RtlDriverTraceReport,
    StatementKind,
    TraceNode,
)
from rtl_agent.signal_source_map_models import (
    DeclarationCandidate,
    SignalMappingStatus,
    SignalSourceMapping,
    SignalSourceMapReport,
)
from rtl_agent.waveform_comparison_models import (
    ComparisonTimeBasis,
    SignalDivergence,
    TimeBasisKind,
    WaveformComparisonReport,
)


def write_comparison(
    tmp_path: Path,
    diverging: list[tuple[str, int, str, str, int]],
    global_earliest: int | None = None,
    name: str = "cmp.json",
) -> Path:
    signals = [
        SignalDivergence(
            name=sig,
            identical=False,
            first_divergence_time=time,
            failing_value_at_divergence=fval,
            passing_value_at_divergence=pval,
            failing_transition_count=1,
            passing_transition_count=1,
            xz_difference=False,
            divergence_duration=5,
            divergence_score=score,
        )
        for sig, time, fval, pval, score in diverging
    ]
    report = WaveformComparisonReport(
        failing_slice_path=tmp_path / "f.json",
        passing_slice_path=tmp_path / "p.json",
        time_basis=ComparisonTimeBasis(
            kind=TimeBasisKind.SHARED_TICKS,
            normalized=False,
            common_start=0,
            common_end=50,
            detail="shared",
        ),
        shared_signal_count=len(signals),
        diverging_signals=signals,
        global_earliest_divergence_time=global_earliest,
    )
    path = tmp_path / name
    path.write_text(json.dumps(report.model_dump(mode="json")), encoding="utf-8")
    return path


def write_signal_map(
    tmp_path: Path,
    mappings: list[tuple[str, str, SignalMappingStatus, list[tuple[str, str, int]]]],
    name: str = "sigmap.json",
) -> Path:
    entries = [
        SignalSourceMapping(
            signal=signal,
            leaf=leaf,
            scope=signal.split(".")[:-1],
            status=status,
            reason="test",
            candidates=[
                DeclarationCandidate(
                    declaration_name=decl_name,
                    declaration_kind="module",
                    file_path=file_path,
                    line=line,
                    matched_element=decl_name,
                    matched_role="scope",
                    match_reason="test",
                    score=100,
                    primary=True,
                )
                for decl_name, file_path, line in decls
            ],
        )
        for signal, leaf, status, decls in mappings
    ]
    report = SignalSourceMapReport(
        repository_map_path=tmp_path / "repo-map.json",
        total_signals=len(entries),
        exact_count=len(entries),
        probable_count=0,
        ambiguous_count=0,
        unresolved_count=0,
        mappings=entries,
    )
    path = tmp_path / name
    path.write_text(json.dumps(report.model_dump(mode="json")), encoding="utf-8")
    return path


def write_driver_trace(
    tmp_path: Path,
    edges: list[tuple[str, str, int]],
    nodes: list[tuple[str, int, bool]],
    unresolved: list[str],
    signal_map_path: Path,
    name: str = "trace.json",
) -> Path:
    report = RtlDriverTraceReport(
        signal_source_map_path=signal_map_path,
        repository_map_path=tmp_path / "repo-map.json",
        repository_root=tmp_path / "repo",
        max_depth=3,
        max_nodes=64,
        dependency_edges=[
            DependencyEdge(
                source_signal=src,
                depends_on=dep,
                label=EvidenceLabel.TEXTUAL,
                statement_kind=StatementKind.CONTINUOUS_ASSIGN,
                evidence_file="rtl/dut.sv",
                evidence_line=line,
            )
            for src, dep, line in edges
        ],
        dependency_nodes=[
            TraceNode(
                identifier=ident, depth=depth, resolved=resolved, driver_count=1 if resolved else 0
            )
            for ident, depth, resolved in nodes
        ],
        unresolved_identifiers=unresolved,
    )
    path = tmp_path / name
    path.write_text(json.dumps(report.model_dump(mode="json")), encoding="utf-8")
    return path


def standard_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    sig_map = write_signal_map(
        tmp_path,
        [
            ("dut.valid", "valid", SignalMappingStatus.EXACT, [("dut", "rtl/dut.sv", 1)]),
            ("dut.a", "a", SignalMappingStatus.EXACT, [("dut", "rtl/dut.sv", 1)]),
        ],
    )
    trace = write_driver_trace(
        tmp_path,
        edges=[("valid", "a", 3), ("valid", "b", 3), ("a", "b", 8)],
        nodes=[("valid", 0, True), ("a", 1, True), ("b", 2, False)],
        unresolved=["b"],
        signal_map_path=sig_map,
    )
    comparison = write_comparison(tmp_path, [("dut.valid", 30, "0", "1", 205)], global_earliest=30)
    return comparison, sig_map, trace


def test_roots_and_node_attributes(tmp_path: Path) -> None:
    comparison, sig_map, trace = standard_inputs(tmp_path)

    report = build_failure_divergence_graph(comparison, sig_map, trace, max_depth=3)

    assert report.root_identifiers == ["valid"]
    assert report.global_earliest_divergence_time == 30
    nodes = {n.identifier: n for n in report.nodes}
    root = nodes["valid"]
    assert root.is_root is True
    assert root.signal == "dut.valid"
    assert root.mapping_status == "exact"
    assert root.divergence is not None
    assert root.divergence.first_divergence_time == 30
    assert root.divergence.failing_value == "0"
    assert len(root.declarations) == 1
    assert root.declarations[0].file_path == "rtl/dut.sv"


def test_edges_carry_evidence_and_label(tmp_path: Path) -> None:
    comparison, sig_map, trace = standard_inputs(tmp_path)

    report = build_failure_divergence_graph(comparison, sig_map, trace, max_depth=3)

    edges = {(e.source, e.target): e for e in report.edges}
    assert ("valid", "a") in edges
    assert edges[("valid", "a")].label == "textual"
    assert edges[("valid", "a")].evidence_file == "rtl/dut.sv"
    assert edges[("valid", "a")].evidence_line == 3


def test_unresolved_identifier_preserved(tmp_path: Path) -> None:
    comparison, sig_map, trace = standard_inputs(tmp_path)

    report = build_failure_divergence_graph(comparison, sig_map, trace, max_depth=3)

    assert "b" in report.unresolved_identifiers
    nodes = {n.identifier: n for n in report.nodes}
    assert nodes["b"].driver_resolved is False
    assert nodes["b"].mapping_status is None


def test_depth_zero_has_no_edges(tmp_path: Path) -> None:
    comparison, sig_map, trace = standard_inputs(tmp_path)

    report = build_failure_divergence_graph(comparison, sig_map, trace, max_depth=0)

    assert report.edges == []
    assert [n.identifier for n in report.nodes] == ["valid"]


def test_node_limit_truncates(tmp_path: Path) -> None:
    comparison, sig_map, trace = standard_inputs(tmp_path)

    report = build_failure_divergence_graph(comparison, sig_map, trace, max_depth=5, max_nodes=1)

    assert report.truncated is True
    assert any("truncated" in warning for warning in report.warnings)


def test_diverging_signal_not_in_signal_map_warns(tmp_path: Path) -> None:
    sig_map = write_signal_map(tmp_path, [])
    trace = write_driver_trace(tmp_path, edges=[], nodes=[], unresolved=[], signal_map_path=sig_map)
    comparison = write_comparison(tmp_path, [("top.dut.state", 10, "x", "0", 100)])

    report = build_failure_divergence_graph(comparison, sig_map, trace)

    assert report.root_identifiers == ["state"]  # textual leaf fallback
    assert any("not found in signal-source map" in w for w in report.warnings)


def test_multiple_diverging_signals_same_leaf_warns(tmp_path: Path) -> None:
    sig_map = write_signal_map(
        tmp_path,
        [
            ("a.q", "q", SignalMappingStatus.EXACT, [("a", "rtl/a.sv", 1)]),
            ("b.q", "q", SignalMappingStatus.EXACT, [("b", "rtl/b.sv", 1)]),
        ],
    )
    trace = write_driver_trace(
        tmp_path, edges=[], nodes=[("q", 0, True)], unresolved=[], signal_map_path=sig_map
    )
    comparison = write_comparison(tmp_path, [("a.q", 40, "0", "1", 10), ("b.q", 20, "1", "0", 10)])

    report = build_failure_divergence_graph(comparison, sig_map, trace)

    assert report.root_identifiers == ["q"]
    assert any("multiple diverging signals map to leaf" in w for w in report.warnings)
    # Deterministic pick: earliest first divergence time wins (b.q at 20).
    root = next(n for n in report.nodes if n.identifier == "q")
    assert root.signal == "b.q"


def test_no_diverging_signals_warns(tmp_path: Path) -> None:
    sig_map = write_signal_map(tmp_path, [])
    trace = write_driver_trace(tmp_path, edges=[], nodes=[], unresolved=[], signal_map_path=sig_map)
    comparison = write_comparison(tmp_path, [])

    report = build_failure_divergence_graph(comparison, sig_map, trace)

    assert report.root_identifiers == []
    assert report.nodes == []
    assert any("no diverging signals" in w for w in report.warnings)


def test_cross_reference_mismatch_warns(tmp_path: Path) -> None:
    comparison, sig_map, _ = standard_inputs(tmp_path)
    other = write_driver_trace(
        tmp_path,
        edges=[("valid", "a", 3)],
        nodes=[("valid", 0, True)],
        unresolved=[],
        signal_map_path=tmp_path / "different-sigmap.json",
    )

    report = build_failure_divergence_graph(comparison, sig_map, other)

    assert any("different signal-source map" in w for w in report.warnings)


def test_deterministic_output(tmp_path: Path) -> None:
    comparison, sig_map, trace = standard_inputs(tmp_path)
    report = build_failure_divergence_graph(comparison, sig_map, trace, max_depth=3)

    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_divergence_graph(report, first)
    write_divergence_graph(report, second)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    assert json.loads(first.read_text(encoding="utf-8"))["schema_version"] == 1


def test_rejects_malformed_comparison(tmp_path: Path) -> None:
    _, sig_map, trace = standard_inputs(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")

    with pytest.raises(FailureDivergenceGraphError, match="could not load comparison report"):
        build_failure_divergence_graph(bad, sig_map, trace)
