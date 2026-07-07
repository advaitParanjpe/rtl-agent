from __future__ import annotations

from rtl_agent.experiment_comparison_models import (
    ExperimentComparison,
    FingerprintRelationship,
    SignalChange,
)
from rtl_agent.hkg import HistoricalMemoryResult
from rtl_agent.intervention_ranking_models import InterventionRanking, RankingFactor
from rtl_agent.mvp_demo_models import CandidateSummary, ExperimentOutcome, OriginalFailure
from rtl_agent.repair_suggestions import generate_repair_suggestions


def _original() -> OriginalFailure:
    return OriginalFailure(
        failure_run="/run",
        run_valid=True,
        earliest_divergence_time=40,
        earliest_divergence_signals=["hold"],
    )


def _candidate(candidate_id: str = "cand-a") -> CandidateSummary:
    return CandidateSummary(
        candidate_id=candidate_id,
        template_kind="hold_register",
        confidence="high_evidence",
        file="rtl/core.sv",
        source_line=6,
        affected_signal="hold",
        hypothesis="probe hold path",
    )


def _outcome(candidate_id: str = "cand-a", effect: str = "failure_removed") -> ExperimentOutcome:
    return ExperimentOutcome(
        intervention_id=candidate_id,
        template_kind="hold_register",
        confidence="high_evidence",
        execution_status="executed",
        observed_effect=effect,
        observed_effect_rationale=f"observed {effect} in experiment",
        artifact_dir=f"/matrix/{candidate_id}",
    )


def _comparison(candidate_id: str = "cand-a") -> ExperimentComparison:
    return ExperimentComparison(
        intervention_id=candidate_id,
        template_kind="hold_register",
        confidence="high_evidence",
        execution_status="executed",
        comparable=False,
        observed_effect="failure_removed",
        fingerprint=FingerprintRelationship(relation="removed"),
        signal_change=SignalChange(removed=["hold"], shared=["dout"]),
        artifact_dir=f"/matrix/{candidate_id}",
        summary="failure no longer reproduced in bounded experiment",
    )


def _ranking(candidate_id: str = "cand-a") -> InterventionRanking:
    return InterventionRanking(
        intervention_id=candidate_id,
        template_kind="hold_register",
        confidence="high_evidence",
        rank=1,
        score=116,
        ranked=True,
        observed_effect="failure_removed",
        result_cluster_id="cluster-x",
        factors=[RankingFactor(factor="observed_effect:failure_removed", points=100)],
        explanation="Observed failure removal and high evidence confidence.",
        evidence_refs=[f"/matrix/{candidate_id}"],
    )


def test_repair_suggestion_from_ranked_counterfactual_evidence() -> None:
    suggestions = generate_repair_suggestions(
        original_failure=_original(),
        intervention_candidates=[_candidate()],
        experiment_outcomes=[_outcome()],
        experiment_comparisons=[_comparison()],
        intervention_rankings=[_ranking()],
        hkg_memory=HistoricalMemoryResult(
            canonical_digest="canon",
            seen_before=True,
            matching_cluster_ids=("cluster-x",),
            prior_member_failures=("prior",),
        ),
    )

    assert [s.suggestion_id for s in suggestions] == ["repair-suggestion:cand-a"]
    suggestion = suggestions[0]
    assert suggestion.confidence == "high_evidence"
    assert suggestion.related_source_locations == ["rtl/core.sv:6"]
    assert suggestion.related_signals == ["dout", "hold"]
    assert suggestion.supporting_interventions == ["cand-a"]
    assert suggestion.supporting_outcomes == ["failure_removed"]
    assert any("ranked #1" in basis for basis in suggestion.evidence_basis)
    assert any("HKG memory" in basis for basis in suggestion.evidence_basis)
    text = suggestion.suggested_area.lower()
    assert text.startswith("inspect")
    assert "fix" not in text
    assert "root-cause" in suggestion.disclaimer


def test_repair_suggestion_falls_back_to_altering_outcome_without_ranking() -> None:
    suggestions = generate_repair_suggestions(
        original_failure=_original(),
        intervention_candidates=[_candidate("cand-b")],
        experiment_outcomes=[_outcome("cand-b", "failure_changed")],
        experiment_comparisons=[],
        intervention_rankings=[],
    )

    assert [s.suggestion_id for s in suggestions] == ["repair-suggestion:cand-b"]
    assert suggestions[0].confidence == "moderate_evidence"


def test_repair_suggestions_empty_when_insufficient_evidence() -> None:
    assert (
        generate_repair_suggestions(
            original_failure=_original(),
            intervention_candidates=[],
            experiment_outcomes=[_outcome()],
            experiment_comparisons=[],
            intervention_rankings=[],
        )
        == []
    )
    assert (
        generate_repair_suggestions(
            original_failure=_original(),
            intervention_candidates=[_candidate()],
            experiment_outcomes=[_outcome(effect="no_observable_effect")],
            experiment_comparisons=[],
            intervention_rankings=[],
        )
        == []
    )


def test_repair_suggestions_are_deterministic() -> None:
    first = generate_repair_suggestions(
        original_failure=_original(),
        intervention_candidates=[_candidate("b"), _candidate("a")],
        experiment_outcomes=[_outcome("b", "failure_changed"), _outcome("a", "failure_removed")],
        experiment_comparisons=[_comparison("a"), _comparison("b")],
        intervention_rankings=[_ranking("b"), _ranking("a")],
    )
    second = generate_repair_suggestions(
        original_failure=_original(),
        intervention_candidates=[_candidate("b"), _candidate("a")],
        experiment_outcomes=[_outcome("b", "failure_changed"), _outcome("a", "failure_removed")],
        experiment_comparisons=[_comparison("a"), _comparison("b")],
        intervention_rankings=[_ranking("b"), _ranking("a")],
    )
    assert [item.model_dump(mode="json") for item in first] == [
        item.model_dump(mode="json") for item in second
    ]
