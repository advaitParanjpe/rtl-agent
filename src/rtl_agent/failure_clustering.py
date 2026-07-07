"""Deterministic clustering of failures by canonical fingerprint identity.

Groups a set of failures into clusters that represent the same or closely related
observed failure behavior, using only the existing fingerprint and comparison
evidence — no new fingerprint algorithm and no causal claim. The primary key is
the canonical fingerprint (stable across benign variations such as differing
timestamps or stimulus lengths), so identical failures and different
manifestations of the same failure land in one cluster while different failure
mechanisms stay separate. The family fingerprint links related clusters, and
failures without a usable canonical fingerprint are left as their own
insufficient-evidence singletons rather than being force-merged.
"""

from __future__ import annotations

from rtl_agent.failure_clustering_models import (
    FailureCluster,
    FailureClusterMember,
    FailureClusterReport,
)
from rtl_agent.failure_fingerprint_models import FailureFingerprintReport

_PARSER_NOTES = [
    "Clustering is deterministic: failures are grouped by an exact canonical-fingerprint match "
    "(equivalent to the fingerprint comparison's canonical_match), clusters and members are "
    "sorted, and the representative is chosen by a fixed evidence-completeness rule.",
    "Clusters share observed failure behavior, not a proven cause; related clusters are linked "
    "only by a shared family fingerprint.",
]


def member_from_fingerprint(
    member_id: str,
    fingerprint: FailureFingerprintReport,
    *,
    observed_outcome: str | None = None,
    artifact_ref: str | None = None,
) -> FailureClusterMember:
    """Build a clustering member from an existing failure fingerprint report."""

    insufficient = bool(fingerprint.insufficient_evidence) or not fingerprint.canonical_digest
    return FailureClusterMember(
        member_id=member_id,
        canonical_digest=fingerprint.canonical_digest or None,
        family_digest=fingerprint.family_digest or None,
        exact_digest=fingerprint.exact_digest or None,
        earliest_divergent_signals=list(fingerprint.earliest_divergent_signals),
        observed_outcome=observed_outcome,
        artifact_ref=artifact_ref,
        insufficient=insufficient,
    )


def cluster_failures(members: list[FailureClusterMember]) -> FailureClusterReport:
    """Cluster failures deterministically by canonical fingerprint identity."""

    ordered = sorted(members, key=lambda m: m.member_id)
    by_canonical: dict[str, list[FailureClusterMember]] = {}
    insufficient: list[FailureClusterMember] = []
    for member in ordered:
        if member.insufficient or not member.canonical_digest:
            insufficient.append(member)
        else:
            by_canonical.setdefault(member.canonical_digest, []).append(member)

    clusters: list[FailureCluster] = []
    for canonical in sorted(by_canonical):
        clusters.append(_canonical_cluster(canonical, by_canonical[canonical]))

    _link_related(clusters)

    for member in insufficient:
        clusters.append(_singleton_cluster(member))

    clusters.sort(key=lambda c: c.cluster_id)
    assignments = {
        member_id: cluster.cluster_id for cluster in clusters for member_id in cluster.members
    }

    return FailureClusterReport(
        total_failures=len(members),
        cluster_count=len(clusters),
        canonical_cluster_count=len(by_canonical),
        insufficient_count=len(insufficient),
        clusters=clusters,
        assignments=dict(sorted(assignments.items())),
        unclustered_member_ids=sorted(m.member_id for m in insufficient),
        parser_notes=_PARSER_NOTES,
    )


def _canonical_cluster(canonical: str, group: list[FailureClusterMember]) -> FailureCluster:
    representative, reason = _representative(group)
    return FailureCluster(
        cluster_id=f"cluster-{canonical[:16]}",
        canonical_digest=canonical,
        insufficient=False,
        size=len(group),
        representative_id=representative.member_id,
        representative_reason=reason,
        members=sorted(m.member_id for m in group),
        member_artifacts=sorted(m.artifact_ref for m in group if m.artifact_ref),
        family_digests=sorted({m.family_digest for m in group if m.family_digest}),
        earliest_divergent_signals=list(representative.earliest_divergent_signals),
        observed_outcome_distribution=_distribution(group),
    )


def _singleton_cluster(member: FailureClusterMember) -> FailureCluster:
    return FailureCluster(
        cluster_id=f"unclustered-{_slug(member.member_id)}",
        canonical_digest=None,
        insufficient=True,
        size=1,
        representative_id=member.member_id,
        representative_reason="only member (insufficient evidence to cluster)",
        members=[member.member_id],
        member_artifacts=[member.artifact_ref] if member.artifact_ref else [],
        family_digests=[member.family_digest] if member.family_digest else [],
        earliest_divergent_signals=list(member.earliest_divergent_signals),
        observed_outcome_distribution=_distribution([member]),
    )


def _representative(group: list[FailureClusterMember]) -> tuple[FailureClusterMember, str]:
    # Most complete evidence first: most earliest-divergent signals, then a
    # present exact digest, then the lexicographically smallest member id.
    ranked = sorted(
        group,
        key=lambda m: (
            -len(m.earliest_divergent_signals),
            m.exact_digest is None,
            m.member_id,
        ),
    )
    best = ranked[0]
    if len(group) == 1:
        reason = "only member of the cluster"
    else:
        reason = (
            f"most complete evidence ({len(best.earliest_divergent_signals)} earliest-divergent "
            "signals; ties broken by exact-digest presence then member id)"
        )
    return best, reason


def _distribution(group: list[FailureClusterMember]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for member in group:
        label = member.observed_outcome or "unspecified"
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


def _link_related(clusters: list[FailureCluster]) -> None:
    families: dict[str, list[str]] = {}
    for cluster in clusters:
        for family in cluster.family_digests:
            families.setdefault(family, []).append(cluster.cluster_id)
    for cluster in clusters:
        related: set[str] = set()
        for family in cluster.family_digests:
            related.update(families.get(family, []))
        related.discard(cluster.cluster_id)
        cluster.related_cluster_ids = sorted(related)


def _slug(value: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in value)[:48] or "member"
