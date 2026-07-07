"""Deterministic construction of the Hardware Knowledge Graph v0.

Converts existing structured, versioned evidence artifacts (a failure-intelligence
run's signal-source map, driver trace, divergence graph, and failure report; its
fingerprint; and, optionally, an experiment-matrix report, a generated
intervention report, and a failure-clustering report) into a typed graph of
nodes and edges. Every node and edge retains provenance back to the artifact it
was built from (artifact id, schema version, content hash/path). Construction and
serialization are deterministic: nodes and edges are keyed by stable ids,
attributes are set first-writer-wins in a fixed ingestion order, provenance is
de-duplicated and sorted, and the final lists are sorted by id. No querying, no
inference, no graph algorithms beyond construction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ValidationError

from rtl_agent.experiment_comparison_models import ExperimentComparison
from rtl_agent.experiment_matrix_models import ExperimentMatrixReport
from rtl_agent.failure_clustering_models import FailureClusterReport
from rtl_agent.failure_divergence_graph_models import FailureDivergenceGraphReport
from rtl_agent.failure_fingerprint import fingerprint_run
from rtl_agent.failure_fingerprint_models import FailureFingerprintReport
from rtl_agent.failure_intelligence_run_models import FailureIntelligenceRunManifest
from rtl_agent.failure_report_models import FailureReport
from rtl_agent.hkg.models import (
    HKG_SCHEMA_VERSION,
    EdgeType,
    HkgEdge,
    HkgGraph,
    HkgNode,
    NodeType,
    Provenance,
)
from rtl_agent.intervention_ranking_models import InterventionRanking
from rtl_agent.intervention_template_models import InterventionTemplateReport
from rtl_agent.rtl_driver_trace_models import RtlDriverTraceReport
from rtl_agent.signal_source_map_models import SignalSourceMapReport

_PARSER_NOTES = [
    "The HKG is built only from structured, versioned artifacts (never from Markdown or "
    "human-readable reports); every node and edge cites its source artifact.",
    "Construction is deterministic (stable ids, fixed ingestion order, sorted provenance and "
    "output) and encodes no causal claim, inference, or query.",
]


class HkgBuildError(RuntimeError):
    pass


@dataclass
class FailureBundle:
    """The loaded structured artifacts for one failure to ingest into the graph."""

    failure_id: str
    manifest: FailureIntelligenceRunManifest
    fingerprint: FailureFingerprintReport
    source_map: SignalSourceMapReport | None = None
    driver_trace: RtlDriverTraceReport | None = None
    divergence: FailureDivergenceGraphReport | None = None
    failure_report: FailureReport | None = None
    matrix: ExperimentMatrixReport | None = None
    matrix_prov: Provenance | None = None
    interventions: InterventionTemplateReport | None = None
    interventions_prov: Provenance | None = None
    experiment_comparisons: list[ExperimentComparison] = field(default_factory=list)
    experiment_comparisons_prov: Provenance | None = None
    intervention_rankings: list[InterventionRanking] = field(default_factory=list)
    intervention_rankings_prov: Provenance | None = None
    _prov_by_kind: dict[str, Provenance] = field(default_factory=dict)


def load_failure_bundle(
    failure_id: str,
    run_dir: Path,
    *,
    matrix_path: Path | None = None,
    interventions_path: Path | None = None,
) -> FailureBundle:
    """Load one failure's structured artifacts from a run directory (+ optional reports)."""

    resolved = run_dir.resolve()
    manifest = _read(resolved / "run-manifest.json", FailureIntelligenceRunManifest, "run manifest")
    prov_by_kind = _provenance_by_kind(manifest)
    paths = _artifact_paths(manifest, resolved)

    bundle = FailureBundle(
        failure_id=failure_id,
        manifest=manifest,
        fingerprint=fingerprint_run(resolved),
        source_map=_read_optional(paths.get("signal_source_map_report"), SignalSourceMapReport),
        driver_trace=_read_optional(paths.get("rtl_driver_trace_report"), RtlDriverTraceReport),
        divergence=_read_optional(
            paths.get("failure_divergence_graph_report"), FailureDivergenceGraphReport
        ),
        failure_report=_read_optional(paths.get("failure_report"), FailureReport),
        _prov_by_kind=prov_by_kind,
    )
    if matrix_path is not None:
        bundle.matrix = _read(matrix_path, ExperimentMatrixReport, "experiment matrix")
        bundle.matrix_prov = _file_provenance("experiment_matrix", matrix_path, bundle.matrix)
    if interventions_path is not None:
        bundle.interventions = _read(
            interventions_path, InterventionTemplateReport, "intervention templates"
        )
        bundle.interventions_prov = _file_provenance(
            "intervention_templates", interventions_path, bundle.interventions
        )
    return bundle


def build_hkg(
    bundles: list[FailureBundle],
    *,
    graph_id: str,
    cluster_report: FailureClusterReport | None = None,
    cluster_report_prov: Provenance | None = None,
) -> HkgGraph:
    """Build a deterministic HKG from one or more failure bundles."""

    builder = _GraphBuilder()
    warnings: list[str] = []
    for bundle in sorted(bundles, key=lambda b: b.failure_id):
        _ingest_failure(builder, bundle, warnings)
    if cluster_report is not None:
        prov = cluster_report_prov or Provenance(
            artifact_id="failure_clustering", schema_version=cluster_report.schema_version
        )
        _ingest_clusters(builder, cluster_report, prov)
    return builder.finalize(graph_id=graph_id, warnings=sorted(dict.fromkeys(warnings)))


# --------------------------------------------------------------------------- #
# Ingestion.
# --------------------------------------------------------------------------- #


def _ingest_failure(builder: _GraphBuilder, bundle: FailureBundle, warnings: list[str]) -> None:
    manifest = bundle.manifest
    manifest_prov = Provenance(
        artifact_id="run_manifest",
        schema_version=manifest.schema_version,
        path="run-manifest.json",
    )
    failure_id = _nid(NodeType.FAILURE, bundle.failure_id)
    builder.node(
        failure_id,
        NodeType.FAILURE,
        bundle.failure_id,
        {"run_id": manifest.run_id, "failure_time": str(manifest.failure_time)},
        manifest_prov,
    )

    fingerprint = bundle.fingerprint
    fp_prov = Provenance(
        artifact_id="failure_fingerprint",
        schema_version=fingerprint.schema_version,
        content_sha256=fingerprint.exact_digest or None,
    )
    if fingerprint.canonical_digest:
        canonical_id = _nid(NodeType.CANONICAL_FINGERPRINT, fingerprint.canonical_digest)
        builder.node(
            canonical_id,
            NodeType.CANONICAL_FINGERPRINT,
            fingerprint.canonical_digest[:16],
            {
                "canonical_digest": fingerprint.canonical_digest,
                "family_digest": fingerprint.family_digest,
                "exact_digest": fingerprint.exact_digest,
            },
            fp_prov,
        )
        builder.edge(
            EdgeType.REFERENCES, failure_id, canonical_id, {"role": "fingerprint"}, fp_prov
        )
    else:
        warnings.append(f"{bundle.failure_id}: no canonical fingerprint (insufficient evidence)")

    _ingest_source_map(builder, bundle)
    _ingest_driver_trace(builder, bundle)
    _ingest_divergence(builder, bundle)
    _ingest_failure_report(builder, bundle, failure_id)
    _ingest_interventions(builder, bundle, failure_id)
    _ingest_matrix(builder, bundle)
    _ingest_experiment_comparisons(builder, bundle)
    _ingest_intervention_rankings(builder, bundle)


def _ingest_source_map(builder: _GraphBuilder, bundle: FailureBundle) -> None:
    if bundle.source_map is None:
        return
    prov = bundle._prov_by_kind.get(
        "signal_source_map_report",
        Provenance(
            artifact_id="signal_source_map_report",
            schema_version=bundle.source_map.schema_version,
        ),
    )
    for mapping in bundle.source_map.mappings:
        signal_id = _signal_node(
            builder, mapping.leaf, {"mapping_status": str(mapping.status)}, prov
        )
        primary = next((c for c in mapping.candidates if c.primary), None)
        if primary is None:
            continue
        location_id = _location_node(builder, primary.file_path, primary.line, prov)
        builder.edge(EdgeType.ORIGINATED_FROM, signal_id, location_id, {}, prov)
        if primary.declaration_kind == "module":
            module_id = _nid(NodeType.MODULE, primary.declaration_name)
            builder.node(
                module_id,
                NodeType.MODULE,
                primary.declaration_name,
                {"file": primary.file_path},
                prov,
            )
            builder.edge(EdgeType.CONTAINS, module_id, signal_id, {}, prov)


def _ingest_driver_trace(builder: _GraphBuilder, bundle: FailureBundle) -> None:
    trace = bundle.driver_trace
    if trace is None:
        return
    prov = bundle._prov_by_kind.get(
        "rtl_driver_trace_report",
        Provenance(artifact_id="rtl_driver_trace_report", schema_version=trace.schema_version),
    )
    for traced in trace.traced_signals:
        signal_id = _signal_node(
            builder,
            traced.leaf,
            {"full_name": traced.signal, "trace_status": str(traced.status)},
            prov,
        )
        for driver in traced.drivers:
            location_id = _location_node(builder, driver.file_path, driver.line, prov)
            builder.edge(
                EdgeType.ORIGINATED_FROM,
                signal_id,
                location_id,
                {"statement_kind": str(driver.kind)},
                prov,
            )
    for edge in trace.dependency_edges:
        source = _signal_node(builder, edge.source_signal, {}, prov)
        target = _signal_node(builder, edge.depends_on, {}, prov)
        builder.edge(
            EdgeType.DEPENDS_ON,
            source,
            target,
            {"label": str(edge.label), "statement_kind": str(edge.statement_kind)},
            prov,
        )


def _ingest_divergence(builder: _GraphBuilder, bundle: FailureBundle) -> None:
    graph = bundle.divergence
    if graph is None:
        return
    prov = bundle._prov_by_kind.get(
        "failure_divergence_graph_report",
        Provenance(
            artifact_id="failure_divergence_graph_report", schema_version=graph.schema_version
        ),
    )
    for node in graph.nodes:
        attributes = {"is_root": str(node.is_root)}
        if node.divergence is not None:
            attributes["divergence_time"] = str(node.divergence.first_divergence_time)
            attributes["failing_value"] = str(node.divergence.failing_value)
            attributes["xz_difference"] = str(node.divergence.xz_difference)
        signal_id = _signal_node(builder, node.identifier, attributes, prov)
        for declaration in node.declarations:
            location_id = _location_node(builder, declaration.file_path, declaration.line, prov)
            builder.edge(EdgeType.ORIGINATED_FROM, signal_id, location_id, {}, prov)
    for edge in graph.edges:
        source = _signal_node(builder, edge.source, {}, prov)
        target = _signal_node(builder, edge.target, {}, prov)
        builder.edge(
            EdgeType.DRIVES,
            source,
            target,
            {"label": edge.label, "statement_kind": edge.statement_kind},
            prov,
        )


def _ingest_failure_report(builder: _GraphBuilder, bundle: FailureBundle, failure_id: str) -> None:
    report = bundle.failure_report
    if report is None:
        return
    prov = bundle._prov_by_kind.get(
        "failure_report",
        Provenance(artifact_id="failure_report", schema_version=report.schema_version),
    )
    for signal in report.earliest_divergence_signals:
        signal_id = _signal_node(builder, signal, {}, prov)
        builder.edge(
            EdgeType.REFERENCES, failure_id, signal_id, {"role": "earliest_divergent"}, prov
        )


def _ingest_interventions(builder: _GraphBuilder, bundle: FailureBundle, failure_id: str) -> None:
    report = bundle.interventions
    if report is None or bundle.interventions_prov is None:
        return
    prov = bundle.interventions_prov
    for candidate in report.candidates:
        intervention_id = _nid(NodeType.INTERVENTION, candidate.candidate_id)
        builder.node(
            intervention_id,
            NodeType.INTERVENTION,
            candidate.candidate_id,
            {
                "template_kind": str(candidate.template_kind),
                "confidence": str(candidate.confidence),
                "affected_signal": candidate.affected_signal,
                "file": candidate.file,
            },
            prov,
        )
        builder.edge(EdgeType.GENERATED, failure_id, intervention_id, {}, prov)
        location_id = _location_node(builder, candidate.source_file, candidate.source_line, prov)
        builder.edge(EdgeType.REFERENCES, intervention_id, location_id, {"role": "edit_site"}, prov)
        signal_id = _signal_node(builder, candidate.affected_signal, {}, prov)
        builder.edge(
            EdgeType.REFERENCES, intervention_id, signal_id, {"role": "affected_signal"}, prov
        )


def _ingest_matrix(builder: _GraphBuilder, bundle: FailureBundle) -> None:
    matrix = bundle.matrix
    if matrix is None or bundle.matrix_prov is None:
        return
    prov = bundle.matrix_prov
    for row in matrix.rows:
        experiment_id = _nid(NodeType.EXPERIMENT, row.intervention_id)
        builder.node(
            experiment_id,
            NodeType.EXPERIMENT,
            row.intervention_id,
            {
                "execution_status": row.execution_status,
                "observed_effect": row.observed_effect,
                "command_status": str(row.command_status),
            },
            prov,
        )
        intervention_id = _nid(NodeType.INTERVENTION, row.intervention_id)
        if intervention_id in builder.nodes:
            builder.edge(
                EdgeType.REFERENCES, experiment_id, intervention_id, {"role": "tested"}, prov
            )
        effect_id = _nid(NodeType.OBSERVED_EFFECT, row.observed_effect)
        builder.node(effect_id, NodeType.OBSERVED_EFFECT, row.observed_effect, {}, prov)
        builder.edge(EdgeType.PRODUCED, experiment_id, effect_id, {}, prov)
        if row.result_canonical_digest:
            canonical_id = _nid(NodeType.CANONICAL_FINGERPRINT, row.result_canonical_digest)
            builder.node(
                canonical_id,
                NodeType.CANONICAL_FINGERPRINT,
                row.result_canonical_digest[:16],
                {"canonical_digest": row.result_canonical_digest},
                prov,
            )
            builder.edge(EdgeType.REFERENCES, experiment_id, canonical_id, {"role": "result"}, prov)


def _ingest_experiment_comparisons(builder: _GraphBuilder, bundle: FailureBundle) -> None:
    if not bundle.experiment_comparisons or bundle.experiment_comparisons_prov is None:
        return
    prov = bundle.experiment_comparisons_prov
    for comparison in sorted(bundle.experiment_comparisons, key=lambda c: c.intervention_id):
        experiment_id = _nid(NodeType.EXPERIMENT, comparison.intervention_id)
        if experiment_id not in builder.nodes:
            builder.node(
                experiment_id,
                NodeType.EXPERIMENT,
                comparison.intervention_id,
                {"execution_status": comparison.execution_status},
                prov,
            )
        builder.node(
            experiment_id,
            NodeType.EXPERIMENT,
            comparison.intervention_id,
            {
                "comparable": str(comparison.comparable),
                "fingerprint_relation": str(comparison.fingerprint.relation),
                "family_changed": str(comparison.family_changed),
                "canonical_changed": str(comparison.canonical_changed),
                "assertion_changed": str(comparison.assertion_changed),
                "summary": comparison.summary,
            },
            prov,
        )
        if comparison.observed_effect:
            effect_id = _nid(NodeType.OBSERVED_EFFECT, comparison.observed_effect)
            builder.node(effect_id, NodeType.OBSERVED_EFFECT, comparison.observed_effect, {}, prov)
            builder.edge(EdgeType.PRODUCED, experiment_id, effect_id, {}, prov)
        if comparison.result_canonical_digest:
            canonical_id = _nid(NodeType.CANONICAL_FINGERPRINT, comparison.result_canonical_digest)
            builder.node(
                canonical_id,
                NodeType.CANONICAL_FINGERPRINT,
                comparison.result_canonical_digest[:16],
                {"canonical_digest": comparison.result_canonical_digest},
                prov,
            )
            builder.edge(EdgeType.REFERENCES, experiment_id, canonical_id, {"role": "result"}, prov)


def _ingest_intervention_rankings(builder: _GraphBuilder, bundle: FailureBundle) -> None:
    if not bundle.intervention_rankings or bundle.intervention_rankings_prov is None:
        return
    prov = bundle.intervention_rankings_prov
    for ranking in sorted(bundle.intervention_rankings, key=lambda r: r.intervention_id):
        intervention_id = _nid(NodeType.INTERVENTION, ranking.intervention_id)
        if intervention_id not in builder.nodes:
            builder.node(
                intervention_id,
                NodeType.INTERVENTION,
                ranking.intervention_id,
                {},
                prov,
            )
        builder.node(
            intervention_id,
            NodeType.INTERVENTION,
            ranking.intervention_id,
            {
                "ranking_rank": "" if ranking.rank is None else str(ranking.rank),
                "ranking_score": str(ranking.score),
                "ranking_ranked": str(ranking.ranked),
                "ranking_observed_effect": ranking.observed_effect,
                "ranking_result_cluster_id": ranking.result_cluster_id or "",
            },
            prov,
        )
        experiment_id = _nid(NodeType.EXPERIMENT, ranking.intervention_id)
        if experiment_id in builder.nodes:
            builder.edge(
                EdgeType.REFERENCES, intervention_id, experiment_id, {"role": "ranking"}, prov
            )
        if ranking.result_cluster_id:
            cluster_id = _nid(NodeType.FAILURE_CLUSTER, ranking.result_cluster_id)
            if cluster_id in builder.nodes:
                builder.edge(
                    EdgeType.REFERENCES,
                    intervention_id,
                    cluster_id,
                    {"role": "ranked_result_cluster"},
                    prov,
                )


def _ingest_clusters(
    builder: _GraphBuilder, report: FailureClusterReport, prov: Provenance
) -> None:
    for cluster in report.clusters:
        cluster_id = _nid(NodeType.FAILURE_CLUSTER, cluster.cluster_id)
        builder.node(
            cluster_id,
            NodeType.FAILURE_CLUSTER,
            cluster.cluster_id,
            {
                "size": str(cluster.size),
                "canonical_digest": str(cluster.canonical_digest),
                "insufficient": str(cluster.insufficient),
            },
            prov,
        )
        for member_id in cluster.members:
            failure_id = _nid(NodeType.FAILURE, member_id)
            if failure_id in builder.nodes:
                builder.edge(EdgeType.BELONGS_TO_CLUSTER, failure_id, cluster_id, {}, prov)
        if cluster.canonical_digest:
            canonical_id = _nid(NodeType.CANONICAL_FINGERPRINT, cluster.canonical_digest)
            if canonical_id in builder.nodes:
                builder.edge(EdgeType.BELONGS_TO_CLUSTER, canonical_id, cluster_id, {}, prov)


# --------------------------------------------------------------------------- #
# Graph accumulator + helpers.
# --------------------------------------------------------------------------- #


class _GraphBuilder:
    def __init__(self) -> None:
        self.nodes: dict[str, HkgNode] = {}
        self.edges: dict[str, HkgEdge] = {}

    def node(
        self,
        node_id: str,
        node_type: NodeType,
        label: str,
        attributes: dict[str, str],
        provenance: Provenance,
    ) -> str:
        existing = self.nodes.get(node_id)
        if existing is None:
            existing = HkgNode(node_id=node_id, type=node_type, label=label, attributes={})
            self.nodes[node_id] = existing
        for key, value in attributes.items():
            existing.attributes.setdefault(key, value)
        _merge_provenance(existing.provenance, provenance)
        return node_id

    def edge(
        self,
        edge_type: EdgeType,
        source: str,
        target: str,
        attributes: dict[str, str],
        provenance: Provenance,
    ) -> None:
        edge_id = f"{edge_type}|{source}|{target}"
        existing = self.edges.get(edge_id)
        if existing is None:
            existing = HkgEdge(
                edge_id=edge_id, type=edge_type, source=source, target=target, attributes={}
            )
            self.edges[edge_id] = existing
        for key, value in attributes.items():
            existing.attributes.setdefault(key, value)
        _merge_provenance(existing.provenance, provenance)

    def finalize(self, *, graph_id: str, warnings: list[str]) -> HkgGraph:
        nodes = sorted(self.nodes.values(), key=lambda n: n.node_id)
        edges = sorted(self.edges.values(), key=lambda e: e.edge_id)
        for node in nodes:
            node.attributes = dict(sorted(node.attributes.items()))
            node.provenance = _sorted_provenance(node.provenance)
        for edge in edges:
            edge.attributes = dict(sorted(edge.attributes.items()))
            edge.provenance = _sorted_provenance(edge.provenance)
        node_type_counts = _counts(str(n.type) for n in nodes)
        edge_type_counts = _counts(str(e.type) for e in edges)
        return HkgGraph(
            schema_version=HKG_SCHEMA_VERSION,
            graph_id=graph_id,
            node_count=len(nodes),
            edge_count=len(edges),
            node_type_counts=node_type_counts,
            edge_type_counts=edge_type_counts,
            nodes=nodes,
            edges=edges,
            warnings=warnings,
            parser_notes=_PARSER_NOTES,
        )


def _signal_node(
    builder: _GraphBuilder, leaf: str, attributes: dict[str, str], prov: Provenance
) -> str:
    return builder.node(_nid(NodeType.SIGNAL, leaf), NodeType.SIGNAL, leaf, attributes, prov)


def _location_node(builder: _GraphBuilder, file_path: str, line: int, prov: Provenance) -> str:
    location = f"{file_path}:{line}"
    return builder.node(
        _nid(NodeType.SOURCE_LOCATION, location),
        NodeType.SOURCE_LOCATION,
        location,
        {"file": file_path, "line": str(line)},
        prov,
    )


def _nid(node_type: NodeType, key: str) -> str:
    return f"{node_type}:{key}"


def _merge_provenance(existing: list[Provenance], provenance: Provenance) -> None:
    if provenance not in existing:
        existing.append(provenance)


def _sorted_provenance(provenance: list[Provenance]) -> list[Provenance]:
    return sorted(
        provenance,
        key=lambda p: (p.artifact_id, p.path or "", p.content_sha256 or "", p.schema_version or 0),
    )


def _counts(values: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:  # type: ignore[attr-defined]
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _provenance_by_kind(manifest: FailureIntelligenceRunManifest) -> dict[str, Provenance]:
    provenance: dict[str, Provenance] = {}
    for artifact in manifest.artifacts:
        provenance.setdefault(
            artifact.kind,
            Provenance(
                artifact_id=artifact.kind,
                schema_version=artifact.schema_version,
                content_sha256=artifact.sha256,
                path=artifact.relative_path,
            ),
        )
    return provenance


def _artifact_paths(manifest: FailureIntelligenceRunManifest, run_dir: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for artifact in manifest.artifacts:
        if artifact.path_kind == "run_relative":
            paths.setdefault(artifact.kind, run_dir / artifact.relative_path)
    if manifest.failure_report_path:
        paths.setdefault("failure_report", run_dir / manifest.failure_report_path)
    return paths


def _file_provenance(artifact_id: str, path: Path, model: BaseModel) -> Provenance:
    from hashlib import sha256

    content = path.read_bytes()
    return Provenance(
        artifact_id=artifact_id,
        schema_version=getattr(model, "schema_version", None),
        content_sha256=sha256(content).hexdigest(),
        path=path.name,
    )


def _read[ModelT: BaseModel](path: Path, model: type[ModelT], label: str) -> ModelT:
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise HkgBuildError(f"{label} is unreadable: {path} ({exc})") from exc


def _read_optional[ModelT: BaseModel](path: Path | None, model: type[ModelT]) -> ModelT | None:
    if path is None or not path.exists():
        return None
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError):
        return None


def serialize_graph(graph: HkgGraph) -> str:
    """Deterministic JSON serialization (fully key-sorted) of a graph."""

    return json.dumps(graph.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def write_graph(graph: HkgGraph, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialize_graph(graph), encoding="utf-8")
