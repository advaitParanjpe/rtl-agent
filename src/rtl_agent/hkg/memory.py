"""Historical failure lookup over Hardware Knowledge Graph v0.

The memory layer is a deterministic read-only projection over the HKG query API.
It answers whether a canonical failure fingerprint already appears in the graph
and summarizes related prior evidence. It does not infer root cause, mutate the
graph, execute tools, or introduce new graph construction semantics.
"""

from __future__ import annotations

from dataclasses import dataclass

from rtl_agent.failure_fingerprint_models import FailureFingerprintReport
from rtl_agent.hkg.models import EdgeType, HkgGraph, HkgNode, NodeType, Provenance
from rtl_agent.hkg.query import HkgQuery, query_graph

HISTORICAL_MEMORY_DISCLAIMER = (
    "Historical memory matches are deterministic lookups over shared canonical fingerprint "
    "and related HKG evidence only. A match is not a causal claim, root-cause claim, or proof "
    "that two failures have the same underlying defect."
)


@dataclass(frozen=True)
class PriorInterventionSummary:
    intervention_id: str
    failure_id: str
    template_kind: str | None = None
    confidence: str | None = None
    ranking_rank: int | None = None
    ranking_score: int | None = None
    ranking_ranked: bool | None = None
    ranking_observed_effect: str | None = None
    ranking_result_cluster_id: str | None = None
    provenance: tuple[Provenance, ...] = ()


@dataclass(frozen=True)
class PriorExperimentSummary:
    intervention_id: str
    experiment_id: str
    observed_effects: tuple[str, ...]
    execution_status: str | None = None
    provenance: tuple[Provenance, ...] = ()


@dataclass(frozen=True)
class HistoricalMemoryResult:
    canonical_digest: str
    seen_before: bool
    matching_cluster_ids: tuple[str, ...] = ()
    prior_member_failures: tuple[str, ...] = ()
    prior_interventions: tuple[PriorInterventionSummary, ...] = ()
    prior_observed_effects: tuple[str, ...] = ()
    prior_experiments: tuple[PriorExperimentSummary, ...] = ()
    provenance: tuple[Provenance, ...] = ()
    disclaimer: str = HISTORICAL_MEMORY_DISCLAIMER


def lookup_historical_failure(
    graph_or_query: HkgGraph | HkgQuery,
    fingerprint_or_canonical: FailureFingerprintReport | str,
    *,
    exclude_source_ids: set[str] | None = None,
) -> HistoricalMemoryResult:
    """Look up prior HKG evidence for one canonical failure fingerprint."""

    query = graph_or_query if isinstance(graph_or_query, HkgQuery) else query_graph(graph_or_query)
    canonical_digest = _canonical_digest(fingerprint_or_canonical)
    if not canonical_digest:
        return HistoricalMemoryResult(canonical_digest="", seen_before=False)

    excluded = exclude_source_ids or set()
    direct_failures = [
        failure
        for failure in query.find_failures_by_canonical_fingerprint(canonical_digest)
        if failure.attributes.get("source_id") not in excluded
    ]
    if not direct_failures:
        return HistoricalMemoryResult(canonical_digest=canonical_digest, seen_before=False)

    cluster_ids = _cluster_ids(query, direct_failures)
    member_failures = [
        failure
        for failure in _member_failures(query, direct_failures, cluster_ids)
        if failure.attributes.get("source_id") not in excluded
    ]
    if not member_failures:
        return HistoricalMemoryResult(canonical_digest=canonical_digest, seen_before=False)
    interventions = _prior_interventions(query, member_failures)
    experiments = _prior_experiments(query, interventions)
    observed_effects = tuple(
        sorted({effect for experiment in experiments for effect in experiment.observed_effects})
    )
    provenance = _result_provenance(query, direct_failures, cluster_ids, interventions, experiments)

    return HistoricalMemoryResult(
        canonical_digest=canonical_digest,
        seen_before=True,
        matching_cluster_ids=tuple(cluster_ids),
        prior_member_failures=tuple(node.label for node in member_failures),
        prior_interventions=tuple(interventions),
        prior_observed_effects=observed_effects,
        prior_experiments=tuple(experiments),
        provenance=provenance,
    )


def _canonical_digest(fingerprint_or_canonical: FailureFingerprintReport | str) -> str:
    if isinstance(fingerprint_or_canonical, str):
        return fingerprint_or_canonical
    return fingerprint_or_canonical.canonical_digest


def _cluster_ids(query: HkgQuery, failures: list[HkgNode]) -> list[str]:
    cluster_ids: set[str] = set()
    for failure in failures:
        for edge in query.outgoing_edges(failure.node_id, EdgeType.BELONGS_TO_CLUSTER):
            target = query.get_node(edge.target)
            if target is not None and str(target.type) == str(NodeType.FAILURE_CLUSTER):
                cluster_ids.add(target.label)
    return sorted(cluster_ids)


def _member_failures(
    query: HkgQuery, direct_failures: list[HkgNode], cluster_ids: list[str]
) -> list[HkgNode]:
    members: dict[str, HkgNode] = {node.node_id: node for node in direct_failures}
    for cluster_id in cluster_ids:
        for member in query.find_cluster_members(cluster_id):
            members[member.node_id] = member
    return [members[node_id] for node_id in sorted(members)]


def _prior_interventions(
    query: HkgQuery, failures: list[HkgNode]
) -> list[PriorInterventionSummary]:
    summaries: list[PriorInterventionSummary] = []
    for failure in failures:
        generated = query.outgoing_edges(failure.node_id, EdgeType.GENERATED)
        for edge in generated:
            intervention = query.get_node(edge.target)
            if intervention is None or str(intervention.type) != str(NodeType.INTERVENTION):
                continue
            attrs = intervention.attributes
            ranking_edges = [
                ranking
                for ranking in query.outgoing_edges(intervention.node_id, EdgeType.REFERENCES)
                if ranking.attributes.get("role") == "ranking"
            ]
            ranking_attrs = ranking_edges[0].attributes if ranking_edges else {}
            summaries.append(
                PriorInterventionSummary(
                    intervention_id=intervention.label,
                    failure_id=failure.label,
                    template_kind=_empty_to_none(attrs.get("template_kind")),
                    confidence=_empty_to_none(attrs.get("confidence")),
                    ranking_rank=_int_or_none(ranking_attrs.get("ranking_rank")),
                    ranking_score=_int_or_none(ranking_attrs.get("ranking_score")),
                    ranking_ranked=_bool_or_none(ranking_attrs.get("ranking_ranked")),
                    ranking_observed_effect=_empty_to_none(
                        ranking_attrs.get("ranking_observed_effect")
                    ),
                    ranking_result_cluster_id=_empty_to_none(
                        ranking_attrs.get("ranking_result_cluster_id")
                    ),
                    provenance=tuple(
                        _dedupe_provenance(
                            [*intervention.provenance, *edge.provenance]
                            + [item for ranking in ranking_edges for item in ranking.provenance]
                        )
                    ),
                )
            )
    return sorted(summaries, key=lambda item: (item.failure_id, item.intervention_id))


def _prior_experiments(
    query: HkgQuery, interventions: list[PriorInterventionSummary]
) -> list[PriorExperimentSummary]:
    summaries: list[PriorExperimentSummary] = []
    for intervention in interventions:
        for result in query.find_experiments_for_intervention(intervention.intervention_id):
            effects = tuple(sorted({node.label for node in result.outcomes}))
            summaries.append(
                PriorExperimentSummary(
                    intervention_id=intervention.intervention_id,
                    experiment_id=result.experiment.label,
                    observed_effects=effects,
                    execution_status=_empty_to_none(
                        result.experiment.attributes.get("execution_status")
                    ),
                    provenance=tuple(result.experiment.provenance),
                )
            )
    return sorted(summaries, key=lambda item: (item.intervention_id, item.experiment_id))


def _result_provenance(
    query: HkgQuery,
    direct_failures: list[HkgNode],
    cluster_ids: list[str],
    interventions: list[PriorInterventionSummary],
    experiments: list[PriorExperimentSummary],
) -> tuple[Provenance, ...]:
    provenance: list[Provenance] = []
    for failure in direct_failures:
        provenance.extend(query.get_provenance(failure.node_id))
    for cluster_id in cluster_ids:
        cluster = next(
            (
                node
                for node in query.list_nodes_by_type(NodeType.FAILURE_CLUSTER)
                if node.label == cluster_id or node.node_id == cluster_id
            ),
            None,
        )
        if cluster is not None:
            provenance.extend(query.get_provenance(cluster.node_id))
    for intervention in interventions:
        provenance.extend(intervention.provenance)
    for experiment in experiments:
        provenance.extend(experiment.provenance)
    return _dedupe_provenance(provenance)


def _dedupe_provenance(provenance: list[Provenance]) -> tuple[Provenance, ...]:
    unique = {
        (p.source_id, p.artifact_id, p.path, p.content_sha256, p.schema_version): p
        for p in provenance
    }
    return tuple(
        unique[key]
        for key in sorted(
            unique,
            key=lambda p: (p[0], p[1], p[2] or "", p[3] or "", p[4] or 0),
        )
    )


def _empty_to_none(value: str | None) -> str | None:
    return value if value else None


def _int_or_none(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _bool_or_none(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    if value == "True":
        return True
    if value == "False":
        return False
    return None
