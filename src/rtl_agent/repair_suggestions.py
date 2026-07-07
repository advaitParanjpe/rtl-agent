"""Deterministic evidence-guided repair-direction suggestions.

Suggestions are derived from existing counterfactual evidence only. They point
engineers at areas to inspect or review; they do not generate code edits, apply
patches, introduce templates, or claim root cause.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from rtl_agent.experiment_comparison_models import ExperimentComparison
from rtl_agent.hkg.memory import HistoricalMemoryResult
from rtl_agent.intervention_ranking_models import InterventionRanking

if TYPE_CHECKING:
    from rtl_agent.mvp_demo_models import CandidateSummary, ExperimentOutcome, OriginalFailure

REPAIR_SUGGESTION_SCHEMA_VERSION = 1

REPAIR_SUGGESTION_DISCLAIMER = (
    "This suggestion is a deterministic repair-direction hint from observed counterfactual "
    "evidence. It is not a patch, generated edit, root-cause claim, causal claim, or proven fix."
)


class RepairSuggestion(BaseModel):
    schema_version: int = REPAIR_SUGGESTION_SCHEMA_VERSION
    suggestion_id: str
    suggested_area: str
    evidence_basis: list[str] = Field(default_factory=list)
    related_source_locations: list[str] = Field(default_factory=list)
    related_signals: list[str] = Field(default_factory=list)
    supporting_interventions: list[str] = Field(default_factory=list)
    supporting_outcomes: list[str] = Field(default_factory=list)
    confidence: str
    disclaimer: str = REPAIR_SUGGESTION_DISCLAIMER


def generate_repair_suggestions(
    *,
    original_failure: OriginalFailure,
    intervention_candidates: list[CandidateSummary],
    experiment_outcomes: list[ExperimentOutcome],
    experiment_comparisons: list[ExperimentComparison],
    intervention_rankings: list[InterventionRanking],
    hkg_memory: HistoricalMemoryResult | None = None,
) -> list[RepairSuggestion]:
    """Generate deterministic inspect/review/check suggestions from existing evidence."""

    if not intervention_candidates or not experiment_outcomes:
        return []

    candidate_by_id = {candidate.candidate_id: candidate for candidate in intervention_candidates}
    outcome_by_id = {outcome.intervention_id: outcome for outcome in experiment_outcomes}
    comparison_by_id = {
        comparison.intervention_id: comparison for comparison in experiment_comparisons
    }
    ranked = [ranking for ranking in intervention_rankings if ranking.ranked]

    suggestions: list[RepairSuggestion] = []
    for ranking in sorted(
        ranked,
        key=lambda item: (item.rank is None, item.rank or 0, -item.score, item.intervention_id),
    ):
        candidate = candidate_by_id.get(ranking.intervention_id)
        outcome = outcome_by_id.get(ranking.intervention_id)
        if candidate is None or outcome is None:
            continue
        if outcome.observed_effect in {"experiment_invalid", "unknown", "no_observable_effect"}:
            continue
        suggestions.append(
            _suggestion_from_evidence(
                candidate=candidate,
                outcome=outcome,
                comparison=comparison_by_id.get(ranking.intervention_id),
                ranking=ranking,
                original_failure=original_failure,
                hkg_memory=hkg_memory,
            )
        )

    if suggestions:
        return _dedupe_suggestions(suggestions)

    altering_outcomes = [
        outcome
        for outcome in sorted(experiment_outcomes, key=lambda item: item.intervention_id)
        if outcome.observed_effect not in {"experiment_invalid", "unknown", "no_observable_effect"}
    ]
    for outcome in altering_outcomes:
        candidate = candidate_by_id.get(outcome.intervention_id)
        if candidate is None:
            continue
        suggestions.append(
            _suggestion_from_evidence(
                candidate=candidate,
                outcome=outcome,
                comparison=comparison_by_id.get(outcome.intervention_id),
                ranking=None,
                original_failure=original_failure,
                hkg_memory=hkg_memory,
            )
        )
    return _dedupe_suggestions(suggestions)


def _suggestion_from_evidence(
    *,
    candidate: CandidateSummary,
    outcome: ExperimentOutcome,
    comparison: ExperimentComparison | None,
    ranking: InterventionRanking | None,
    original_failure: OriginalFailure,
    hkg_memory: HistoricalMemoryResult | None,
) -> RepairSuggestion:
    location = f"{candidate.file}:{candidate.source_line}"
    basis = [
        f"intervention `{candidate.candidate_id}` observed `{outcome.observed_effect}`",
        f"candidate confidence `{candidate.confidence}`",
    ]
    if outcome.observed_effect_rationale:
        basis.append(outcome.observed_effect_rationale)
    if comparison is not None and comparison.summary:
        basis.append(comparison.summary)
    if ranking is not None:
        basis.append(f"ranked #{ranking.rank} with score {ranking.score}: {ranking.explanation}")
    if hkg_memory is not None and hkg_memory.seen_before:
        basis.append(
            "HKG memory found shared canonical fingerprint evidence in cluster(s): "
            + ", ".join(hkg_memory.matching_cluster_ids)
        )

    signals = {candidate.affected_signal, *original_failure.earliest_divergence_signals}
    if comparison is not None:
        signals.update(comparison.signal_change.shared)
        signals.update(comparison.signal_change.added)
        signals.update(comparison.signal_change.removed)

    supporting_outcomes = [outcome.observed_effect]
    if ranking is not None and ranking.observed_effect not in supporting_outcomes:
        supporting_outcomes.append(ranking.observed_effect)

    return RepairSuggestion(
        suggestion_id=f"repair-suggestion:{candidate.candidate_id}",
        suggested_area=(
            f"Inspect `{location}` and related signal `{candidate.affected_signal}` because "
            f"the counterfactual evidence for `{candidate.candidate_id}` altered the observed "
            "failure behavior."
        ),
        evidence_basis=sorted(dict.fromkeys(basis)),
        related_source_locations=[location],
        related_signals=sorted(signal for signal in signals if signal),
        supporting_interventions=[candidate.candidate_id],
        supporting_outcomes=sorted(supporting_outcomes),
        confidence=_confidence(candidate, outcome, comparison, ranking, hkg_memory),
    )


def _confidence(
    candidate: CandidateSummary,
    outcome: ExperimentOutcome,
    comparison: ExperimentComparison | None,
    ranking: InterventionRanking | None,
    hkg_memory: HistoricalMemoryResult | None,
) -> str:
    points = 0
    if candidate.confidence == "high_evidence":
        points += 2
    elif candidate.confidence == "moderate_evidence":
        points += 1
    if outcome.observed_effect in {"failure_removed", "failure_changed", "new_failure"}:
        points += 2
    elif outcome.observed_effect in {"failure_delayed", "failure_advanced"}:
        points += 1
    if comparison is not None and comparison.summary:
        points += 1
    if ranking is not None and ranking.ranked:
        points += 1
    if hkg_memory is not None and hkg_memory.seen_before:
        points += 1
    if points >= 6:
        return "high_evidence"
    if points >= 3:
        return "moderate_evidence"
    return "low_evidence"


def _dedupe_suggestions(suggestions: list[RepairSuggestion]) -> list[RepairSuggestion]:
    by_id: dict[str, RepairSuggestion] = {}
    for suggestion in suggestions:
        by_id.setdefault(suggestion.suggestion_id, suggestion)
    return [by_id[key] for key in sorted(by_id)]
