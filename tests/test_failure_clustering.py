from __future__ import annotations

from rtl_agent.failure_clustering import cluster_failures, member_from_fingerprint
from rtl_agent.failure_clustering_models import FailureClusterMember
from rtl_agent.failure_fingerprint_models import FailureFingerprintReport, FingerprintDigest


def _member(
    member_id: str,
    *,
    canonical: str | None = "canon-A",
    family: str | None = "fam-A",
    exact: str | None = "exact-A",
    signals: list[str] | None = None,
    outcome: str | None = None,
    artifact: str | None = None,
    insufficient: bool = False,
) -> FailureClusterMember:
    return FailureClusterMember(
        member_id=member_id,
        canonical_digest=canonical,
        family_digest=family,
        exact_digest=exact,
        earliest_divergent_signals=signals if signals is not None else ["sig"],
        observed_outcome=outcome,
        artifact_ref=artifact,
        insufficient=insufficient,
    )


def test_identical_failures_cluster_together() -> None:
    report = cluster_failures([_member("run-a"), _member("run-b"), _member("run-c")])
    assert report.canonical_cluster_count == 1
    assert len(report.clusters) == 1
    cluster = report.clusters[0]
    assert cluster.size == 3
    assert cluster.members == ["run-a", "run-b", "run-c"]
    assert set(report.assignments.values()) == {cluster.cluster_id}


def test_different_manifestations_of_same_failure_cluster_together() -> None:
    # Same canonical fingerprint but different family/exact digests and different
    # earliest divergence signals count (a full vs a minimized reproduction).
    full = _member("full", family="fam-full", exact="exact-full", signals=["a", "b", "c"])
    mini = _member("mini", family="fam-mini", exact="exact-mini", signals=["a", "b"])
    report = cluster_failures([full, mini])
    assert report.canonical_cluster_count == 1
    cluster = report.clusters[0]
    assert cluster.size == 2
    assert sorted(cluster.members) == ["full", "mini"]
    # Both family digests are recorded, and the representative is the richer one.
    assert cluster.family_digests == ["fam-full", "fam-mini"]
    assert cluster.representative_id == "full"
    assert "most complete evidence" in cluster.representative_reason


def test_different_mechanisms_remain_separate() -> None:
    report = cluster_failures(
        [
            _member("fsm", canonical="canon-fsm", family="fam-fsm"),
            _member("fifo", canonical="canon-fifo", family="fam-fifo"),
            _member("counter", canonical="canon-counter", family="fam-counter"),
        ]
    )
    assert report.canonical_cluster_count == 3
    assert len({c.canonical_digest for c in report.clusters}) == 3
    assert all(c.size == 1 for c in report.clusters)
    # Distinct families -> no related-cluster links.
    assert all(c.related_cluster_ids == [] for c in report.clusters)


def test_shared_family_links_related_clusters() -> None:
    report = cluster_failures(
        [
            _member("x", canonical="canon-x", family="fam-shared"),
            _member("y", canonical="canon-y", family="fam-shared"),
        ]
    )
    assert report.canonical_cluster_count == 2
    ids = {c.cluster_id for c in report.clusters}
    for cluster in report.clusters:
        assert set(cluster.related_cluster_ids) == ids - {cluster.cluster_id}


def test_insufficient_evidence_is_a_singleton_and_not_merged() -> None:
    report = cluster_failures(
        [
            _member("good-1", canonical="canon-A"),
            _member("bad-1", canonical=None, insufficient=True),
            _member("bad-2", canonical=None, insufficient=True),
        ]
    )
    assert report.canonical_cluster_count == 1
    assert report.insufficient_count == 2
    assert sorted(report.unclustered_member_ids) == ["bad-1", "bad-2"]
    singletons = [c for c in report.clusters if c.insufficient]
    assert len(singletons) == 2
    assert all(c.size == 1 for c in singletons)
    # Every failure received a cluster assignment and representative.
    assert set(report.assignments) == {"good-1", "bad-1", "bad-2"}
    assert all(c.representative_id in c.members for c in report.clusters)


def test_outcome_distribution_and_artifacts() -> None:
    report = cluster_failures(
        [
            _member("a", outcome="failed", artifact="rows/a"),
            _member("b", outcome="failed", artifact="rows/b"),
            _member("c", outcome="timeout", artifact="rows/c"),
        ]
    )
    cluster = report.clusters[0]
    assert cluster.observed_outcome_distribution == {"failed": 2, "timeout": 1}
    assert cluster.member_artifacts == ["rows/a", "rows/b", "rows/c"]


def test_clustering_is_deterministic_and_ordered() -> None:
    members = [
        _member("z", canonical="canon-2"),
        _member("a", canonical="canon-1"),
        _member("m", canonical="canon-2"),
    ]
    first = cluster_failures(members)
    second = cluster_failures(list(reversed(members)))
    assert first.model_dump() == second.model_dump()
    assert [c.cluster_id for c in first.clusters] == sorted(c.cluster_id for c in first.clusters)


def test_member_from_fingerprint() -> None:
    fp = FailureFingerprintReport(
        exact_digest="e",
        family_digest="f",
        canonical_digest="c",
        digest=FingerprintDigest(exact="e", family="f", canonical="c"),
        earliest_divergent_signals=["payload_out"],
    )
    member = member_from_fingerprint("run-1", fp, observed_outcome="failed", artifact_ref="ref")
    assert member.canonical_digest == "c"
    assert member.family_digest == "f"
    assert member.earliest_divergent_signals == ["payload_out"]
    assert member.insufficient is False

    insufficient_fp = FailureFingerprintReport(
        exact_digest="e",
        family_digest="f",
        canonical_digest="",
        digest=FingerprintDigest(exact="e", family="f"),
        insufficient_evidence=["missing earliest divergent signal evidence"],
    )
    bad = member_from_fingerprint("run-2", insufficient_fp)
    assert bad.insufficient is True
    assert bad.canonical_digest is None
