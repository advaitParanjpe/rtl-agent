from __future__ import annotations

import json
from collections import deque
from pathlib import Path

from pydantic import BaseModel, ValidationError

from rtl_agent.failure_divergence_graph_models import (
    FailureDivergenceGraphReport,
    GraphEdge,
    GraphNode,
    NodeDeclaration,
    NodeDivergence,
)
from rtl_agent.rtl_driver_trace_models import RtlDriverTraceReport
from rtl_agent.signal_source_map_models import SignalSourceMapReport
from rtl_agent.waveform_comparison_models import SignalDivergence, WaveformComparisonReport


class FailureDivergenceGraphError(RuntimeError):
    pass


def build_failure_divergence_graph(
    comparison_path: Path,
    signal_source_map_path: Path,
    driver_trace_path: Path,
    *,
    max_depth: int = 3,
    max_nodes: int = 128,
) -> FailureDivergenceGraphReport:
    if max_depth < 0:
        raise FailureDivergenceGraphError("max depth must not be negative")
    if max_nodes < 1:
        raise FailureDivergenceGraphError("max nodes must be at least 1")

    comparison = _load(comparison_path, WaveformComparisonReport, "comparison")
    signal_map = _load(signal_source_map_path, SignalSourceMapReport, "signal-source map")
    driver_trace = _load(driver_trace_path, RtlDriverTraceReport, "driver-trace")

    warnings: list[str] = []
    _check_cross_reference(signal_source_map_path, driver_trace, warnings)

    leaf_of_signal = {mapping.signal: mapping.leaf for mapping in signal_map.mappings}
    mapping_status_by_leaf: dict[str, str] = {}
    declarations_by_leaf: dict[str, list[NodeDeclaration]] = {}
    for mapping in signal_map.mappings:
        mapping_status_by_leaf.setdefault(mapping.leaf, str(mapping.status))
        bucket = declarations_by_leaf.setdefault(mapping.leaf, [])
        for candidate in mapping.candidates:
            declaration = NodeDeclaration(
                declaration_name=candidate.declaration_name,
                declaration_kind=candidate.declaration_kind,
                file_path=candidate.file_path,
                line=candidate.line,
            )
            if declaration not in bucket:
                bucket.append(declaration)

    divergence_by_leaf: dict[str, SignalDivergence] = {}
    signal_by_leaf: dict[str, str] = {}
    roots: list[str] = []
    for diverging in comparison.diverging_signals:
        if diverging.name not in leaf_of_signal:
            warnings.append(f"diverging signal not found in signal-source map: {diverging.name}")
        leaf = leaf_of_signal.get(diverging.name, diverging.name.rsplit(".", 1)[-1])
        if leaf in divergence_by_leaf and divergence_by_leaf[leaf].name != diverging.name:
            warnings.append(f"multiple diverging signals map to leaf '{leaf}'")
            if not _prefer(diverging, divergence_by_leaf[leaf]):
                continue
        divergence_by_leaf[leaf] = diverging
        signal_by_leaf[leaf] = diverging.name
        roots.append(leaf)
    roots = sorted(dict.fromkeys(roots))
    if not roots:
        warnings.append("comparison report has no diverging signals to root the graph")

    adjacency: dict[str, list[GraphEdge]] = {}
    for edge in driver_trace.dependency_edges:
        adjacency.setdefault(edge.source_signal, []).append(
            GraphEdge(
                source=edge.source_signal,
                target=edge.depends_on,
                label=str(edge.label),
                statement_kind=str(edge.statement_kind),
                evidence_file=edge.evidence_file,
                evidence_line=edge.evidence_line,
            )
        )
    driver_nodes = {node.identifier: node for node in driver_trace.dependency_nodes}

    visited, edges, truncated = _traverse(roots, adjacency, max_depth, max_nodes)
    if truncated:
        warnings.append(f"graph truncated at max_depth={max_depth}/max_nodes={max_nodes}")

    root_set = set(roots)
    nodes: list[GraphNode] = []
    unresolved: list[str] = []
    for identifier in sorted(visited):
        driver_node = driver_nodes.get(identifier)
        resolved = driver_node.resolved if driver_node is not None else None
        if resolved is not True:
            unresolved.append(identifier)
        divergence = divergence_by_leaf.get(identifier)
        nodes.append(
            GraphNode(
                identifier=identifier,
                depth=visited[identifier],
                is_root=identifier in root_set,
                signal=signal_by_leaf.get(identifier),
                mapping_status=mapping_status_by_leaf.get(identifier),
                driver_resolved=resolved,
                driver_count=driver_node.driver_count if driver_node is not None else None,
                divergence=_node_divergence(divergence) if divergence is not None else None,
                declarations=declarations_by_leaf.get(identifier, []),
            )
        )

    return FailureDivergenceGraphReport(
        comparison_path=comparison_path.resolve(),
        signal_source_map_path=signal_source_map_path.resolve(),
        driver_trace_path=driver_trace_path.resolve(),
        max_depth=max_depth,
        max_nodes=max_nodes,
        root_identifiers=roots,
        global_earliest_divergence_time=comparison.global_earliest_divergence_time,
        nodes=nodes,
        edges=edges,
        unresolved_identifiers=sorted(dict.fromkeys(unresolved)),
        truncated=truncated,
        warnings=sorted(dict.fromkeys(warnings)),
        parser_notes=[
            "The failure divergence graph is composed strictly from existing comparison, "
            "signal-source-map, and driver-trace artifacts; it performs no new RTL scanning "
            "or analysis.",
            "Edges carry the driver-trace evidence label (textual / inferred_textual) and cite "
            "their source location; nothing is asserted as semantic, causal, or a root cause.",
        ],
    )


def write_divergence_graph(report: FailureDivergenceGraphReport, output: Path) -> None:
    if output.exists() and output.is_dir():
        raise FailureDivergenceGraphError(f"output path is a directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _traverse(
    roots: list[str],
    adjacency: dict[str, list[GraphEdge]],
    max_depth: int,
    max_nodes: int,
) -> tuple[dict[str, int], list[GraphEdge], bool]:
    visited: dict[str, int] = {}
    edges: list[GraphEdge] = []
    truncated = False
    queue: deque[tuple[str, int]] = deque((root, 0) for root in roots)
    while queue:
        identifier, depth = queue.popleft()
        if identifier in visited:
            continue
        if len(visited) >= max_nodes:
            truncated = True
            break
        visited[identifier] = depth
        if depth >= max_depth:
            continue
        for edge in adjacency.get(identifier, []):
            edges.append(edge)
            queue.append((edge.target, depth + 1))
    edges = _dedupe_edges(edges)
    edges.sort(key=lambda item: (item.source, item.target, item.evidence_file, item.evidence_line))
    return visited, edges, truncated


def _dedupe_edges(edges: list[GraphEdge]) -> list[GraphEdge]:
    seen: set[tuple[str, str, str, str, int]] = set()
    result: list[GraphEdge] = []
    for edge in edges:
        key = (
            edge.source,
            edge.target,
            edge.statement_kind,
            edge.evidence_file,
            edge.evidence_line,
        )
        if key not in seen:
            seen.add(key)
            result.append(edge)
    return result


def _node_divergence(divergence: SignalDivergence) -> NodeDivergence:
    return NodeDivergence(
        first_divergence_time=divergence.first_divergence_time,
        failing_value=divergence.failing_value_at_divergence,
        passing_value=divergence.passing_value_at_divergence,
        divergence_score=divergence.divergence_score,
        xz_difference=divergence.xz_difference,
    )


def _prefer(candidate: SignalDivergence, current: SignalDivergence) -> bool:
    candidate_key = (
        candidate.first_divergence_time if candidate.first_divergence_time is not None else 1 << 62,
        candidate.name,
    )
    current_key = (
        current.first_divergence_time if current.first_divergence_time is not None else 1 << 62,
        current.name,
    )
    return candidate_key < current_key


def _check_cross_reference(
    signal_source_map_path: Path, driver_trace: RtlDriverTraceReport, warnings: list[str]
) -> None:
    recorded = driver_trace.signal_source_map_path
    if recorded.resolve() != signal_source_map_path.resolve():
        warnings.append(
            "driver-trace was produced from a different signal-source map "
            f"({recorded}); composition may be inconsistent"
        )


def _load[ModelT: BaseModel](path: Path, model: type[ModelT], label: str) -> ModelT:
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise FailureDivergenceGraphError(f"could not load {label} report: {path}") from exc
