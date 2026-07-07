"""Deterministic ranking of intervention candidates by counterfactual informativeness.

Ranks completed experiment results using only the evidence already collected —
the observed-effect label, the fingerprint relationship, the comparison object,
result-cluster membership, and execution validity — so engineers can find the
most informative counterfactuals first. It runs no new analysis, adds no causal
claim, and never ranks an experiment that did not produce a comparable
observation (those are recorded as unranked with a reason). Scoring is a fixed
sum of integer factors and ties break on the intervention id, so the ranking is
byte-deterministic.
"""

from __future__ import annotations

from rtl_agent.experiment_comparison_models import ExperimentComparison
from rtl_agent.failure_clustering import cluster_failures
from rtl_agent.failure_clustering_models import FailureClusterMember
from rtl_agent.intervention_ranking_models import InterventionRanking, RankingFactor

# Base informativeness of each observed effect. A removed failure is the strongest
# signal about what is involved; a no-observable-effect edit is the weakest.
_EFFECT_SCORE = {
    "failure_removed": 100,
    "new_failure": 70,
    "failure_changed": 60,
    "failure_delayed": 50,
    "failure_advanced": 50,
    "no_observable_effect": 10,
    "unknown": 5,
}
# Experiments that produced no comparable observation are not ranked.
_UNRANKED_EFFECTS = {"experiment_invalid"}
_CONFIDENCE_BONUS = {"high_evidence": 6, "moderate_evidence": 3, "low_evidence": 1}


def rank_interventions(comparisons: list[ExperimentComparison]) -> list[InterventionRanking]:
    """Rank interventions deterministically from their experiment comparisons."""

    cluster_by_id, size_by_id = _result_clusters(comparisons)

    rankings: list[InterventionRanking] = []
    for cmp in comparisons:
        cluster_id = cluster_by_id.get(cmp.intervention_id)
        cluster_size = size_by_id.get(cmp.intervention_id)
        rankings.append(_score(cmp, cluster_id, cluster_size))

    ranked = sorted(
        (r for r in rankings if r.ranked),
        key=lambda r: (-r.score, r.intervention_id),
    )
    for position, ranking in enumerate(ranked, start=1):
        ranking.rank = position

    # Deterministic output order: ranked first (by rank), then unranked by id.
    rankings.sort(key=lambda r: (r.rank is None, r.rank or 0, r.intervention_id))
    return rankings


def _score(
    cmp: ExperimentComparison, cluster_id: str | None, cluster_size: int | None
) -> InterventionRanking:
    evidence_refs = _evidence_refs(cmp, cluster_id)

    if cmp.execution_status != "executed" or cmp.observed_effect in _UNRANKED_EFFECTS:
        reason = (
            "; ".join(cmp.unsupported_reasons)
            if cmp.unsupported_reasons
            else "the experiment produced no comparable observation to rank"
        )
        return InterventionRanking(
            intervention_id=cmp.intervention_id,
            template_kind=cmp.template_kind,
            confidence=cmp.confidence,
            ranked=False,
            score=0,
            observed_effect=cmp.observed_effect,
            result_cluster_id=cluster_id,
            result_cluster_size=cluster_size,
            explanation=f"Unranked: {reason}.",
            evidence_refs=evidence_refs,
            unranked_reason=reason,
        )

    factors: list[RankingFactor] = []
    base = _EFFECT_SCORE.get(cmp.observed_effect, _EFFECT_SCORE["unknown"])
    factors.append(RankingFactor(factor=f"observed_effect:{cmp.observed_effect}", points=base))

    if cmp.observed_effect == "failure_removed":
        factors.append(RankingFactor(factor="removed_distinct", points=10))
    elif cmp.canonical_changed:
        factors.append(RankingFactor(factor="canonical_fingerprint_changed", points=15))
    elif cmp.family_changed:
        factors.append(RankingFactor(factor="family_fingerprint_changed", points=10))

    conf_bonus = _CONFIDENCE_BONUS.get(cmp.confidence or "", 0)
    if conf_bonus:
        factors.append(RankingFactor(factor=f"confidence:{cmp.confidence}", points=conf_bonus))

    if cluster_size is not None:
        if cluster_size == 1:
            factors.append(RankingFactor(factor="unique_result_cluster", points=8))
        elif cluster_size == 2:
            factors.append(RankingFactor(factor="near_unique_result_cluster", points=4))

    score = sum(f.points for f in factors)
    return InterventionRanking(
        intervention_id=cmp.intervention_id,
        template_kind=cmp.template_kind,
        confidence=cmp.confidence,
        ranked=True,
        score=score,
        observed_effect=cmp.observed_effect,
        result_cluster_id=cluster_id,
        result_cluster_size=cluster_size,
        factors=factors,
        explanation=_explanation(factors, score),
        evidence_refs=evidence_refs,
    )


def _result_clusters(
    comparisons: list[ExperimentComparison],
) -> tuple[dict[str, str], dict[str, int]]:
    members = [
        FailureClusterMember(
            member_id=cmp.intervention_id,
            canonical_digest=cmp.result_canonical_digest,
            family_digest=cmp.result_family_digest,
            exact_digest=cmp.result_exact_digest,
            insufficient=not cmp.comparable,
            artifact_ref=cmp.artifact_dir,
        )
        for cmp in comparisons
    ]
    report = cluster_failures(members)
    size_by_cluster = {cluster.cluster_id: cluster.size for cluster in report.clusters}
    cluster_by_id = report.assignments
    size_by_id = {
        member_id: size_by_cluster.get(cluster_id, 1)
        for member_id, cluster_id in cluster_by_id.items()
    }
    return cluster_by_id, size_by_id


def _evidence_refs(cmp: ExperimentComparison, cluster_id: str | None) -> list[str]:
    refs: list[str] = []
    if cmp.artifact_dir:
        refs.append(f"artifact:{cmp.artifact_dir}")
    if cluster_id:
        refs.append(f"result_cluster:{cluster_id}")
    if cmp.result_family_digest:
        refs.append(f"result_family:{cmp.result_family_digest[:12]}")
    return refs


def _explanation(factors: list[RankingFactor], score: int) -> str:
    parts = "; ".join(f"{f.factor}=+{f.points}" for f in factors)
    return f"{parts}; total={score}"
