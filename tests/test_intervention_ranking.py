from __future__ import annotations

from rtl_agent.experiment_comparison_models import ExperimentComparison
from rtl_agent.intervention_ranking import rank_interventions
from rtl_agent.intervention_ranking_models import InterventionRanking


def _cmp(
    intervention_id: str,
    observed_effect: str,
    *,
    confidence: str = "moderate_evidence",
    comparable: bool = True,
    family_changed: bool = False,
    canonical_changed: bool = False,
    result_canonical: str | None = None,
    result_family: str | None = None,
    unsupported: list[str] | None = None,
) -> ExperimentComparison:
    return ExperimentComparison(
        intervention_id=intervention_id,
        template_kind="hold_register",
        confidence=confidence,
        execution_status="executed",
        comparable=comparable,
        observed_effect=observed_effect,
        family_changed=family_changed,
        canonical_changed=canonical_changed,
        result_canonical_digest=result_canonical,
        result_family_digest=result_family,
        artifact_dir=f"rows/{intervention_id}",
        unsupported_reasons=unsupported or [],
    )


def _by_id(rankings: list[InterventionRanking]) -> dict[str, InterventionRanking]:
    return {r.intervention_id: r for r in rankings}


def test_removed_ranks_above_no_effect() -> None:
    rankings = rank_interventions(
        [
            _cmp("noeffect", "no_observable_effect", result_canonical="c-same", result_family="f"),
            _cmp("removed", "failure_removed", comparable=False),
        ]
    )
    by_id = _by_id(rankings)
    assert by_id["removed"].score > by_id["noeffect"].score
    assert by_id["removed"].rank == 1
    assert by_id["noeffect"].rank == 2
    assert rankings[0].intervention_id == "removed"


def test_canonical_change_scores_higher_than_family_only() -> None:
    rankings = _by_id(
        rank_interventions(
            [
                _cmp(
                    "canon",
                    "failure_changed",
                    family_changed=True,
                    canonical_changed=True,
                    result_canonical="c-1",
                    result_family="f-1",
                ),
                _cmp(
                    "fam",
                    "failure_changed",
                    family_changed=True,
                    canonical_changed=False,
                    result_canonical="c-2",
                    result_family="f-2",
                ),
            ]
        )
    )
    assert rankings["canon"].score > rankings["fam"].score


def test_invalid_experiment_is_unranked() -> None:
    rankings = _by_id(
        rank_interventions(
            [
                _cmp("ok", "failure_removed", comparable=False),
                _cmp(
                    "bad",
                    "experiment_invalid",
                    comparable=False,
                    unsupported=["command did not run to completion"],
                ),
            ]
        )
    )
    assert rankings["bad"].ranked is False
    assert rankings["bad"].rank is None
    assert rankings["bad"].score == 0
    assert rankings["bad"].unranked_reason == "command did not run to completion"
    assert "Unranked" in rankings["bad"].explanation
    assert rankings["ok"].rank == 1


def test_confidence_breaks_ties() -> None:
    rankings = _by_id(
        rank_interventions(
            [
                _cmp(
                    "low",
                    "failure_changed",
                    confidence="low_evidence",
                    canonical_changed=True,
                    result_canonical="c-a",
                    result_family="f-a",
                ),
                _cmp(
                    "high",
                    "failure_changed",
                    confidence="high_evidence",
                    canonical_changed=True,
                    result_canonical="c-b",
                    result_family="f-b",
                ),
            ]
        )
    )
    assert rankings["high"].score > rankings["low"].score
    assert rankings["high"].rank == 1


def test_unique_result_cluster_scores_higher_than_shared() -> None:
    # Two interventions produce the SAME result fingerprint (shared cluster),
    # one produces a unique result.
    rankings = _by_id(
        rank_interventions(
            [
                _cmp(
                    "shared-a",
                    "failure_changed",
                    canonical_changed=True,
                    result_canonical="c-shared",
                    result_family="f-shared",
                ),
                _cmp(
                    "shared-b",
                    "failure_changed",
                    canonical_changed=True,
                    result_canonical="c-shared",
                    result_family="f-shared",
                ),
                _cmp(
                    "unique",
                    "failure_changed",
                    canonical_changed=True,
                    result_canonical="c-unique",
                    result_family="f-unique",
                ),
            ]
        )
    )
    assert rankings["unique"].result_cluster_size == 1
    assert rankings["shared-a"].result_cluster_size == 2
    assert rankings["unique"].score > rankings["shared-a"].score


def test_ranking_is_deterministic_with_id_tiebreak() -> None:
    members = [
        _cmp(
            "zebra",
            "failure_changed",
            canonical_changed=True,
            result_canonical="c-z",
            result_family="f-z",
        ),
        _cmp(
            "alpha",
            "failure_changed",
            canonical_changed=True,
            result_canonical="c-a",
            result_family="f-a",
        ),
    ]
    first = rank_interventions(members)
    second = rank_interventions(list(reversed(members)))
    assert [r.intervention_id for r in first] == [r.intervention_id for r in second]
    # Equal scores -> alphabetical id wins the higher rank.
    assert first[0].intervention_id == "alpha"
    assert [r.model_dump() for r in first] == [r.model_dump() for r in second]


def test_explanation_and_evidence_refs_populated() -> None:
    (ranking,) = rank_interventions(
        [
            _cmp(
                "x",
                "failure_changed",
                canonical_changed=True,
                result_canonical="c-x",
                result_family="f-x",
            )
        ]
    )
    assert ranking.ranked is True
    assert "total=" in ranking.explanation
    assert any(ref.startswith("artifact:") for ref in ranking.evidence_refs)
    assert any(ref.startswith("result_cluster:") for ref in ranking.evidence_refs)
    assert {f.factor for f in ranking.factors}
