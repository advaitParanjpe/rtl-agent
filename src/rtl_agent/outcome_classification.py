"""Deterministic classification of counterfactual experiment outcomes.

Given the already-computed evidence for one intervention experiment (its
execution/command status and the result fingerprint compared against the
original failure — family digest, earliest failure time, and failing signals),
this maps the experiment to exactly one observed-effect label. It is a pure
comparison over existing evidence: no new analysis, no simulation, and no causal
claim. The returned rationale cites the compared evidence so each label is
auditable against the preserved per-experiment artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ObservedEffect(StrEnum):
    FAILURE_REMOVED = "failure_removed"
    FAILURE_DELAYED = "failure_delayed"
    FAILURE_ADVANCED = "failure_advanced"
    FAILURE_CHANGED = "failure_changed"
    NO_OBSERVABLE_EFFECT = "no_observable_effect"
    NEW_FAILURE = "new_failure"
    EXPERIMENT_INVALID = "experiment_invalid"
    UNKNOWN = "unknown"


_INVALID_COMMAND_STATUSES = frozenset({"timeout", "exec_error"})


@dataclass(frozen=True)
class OutcomeEvidence:
    """The existing evidence a single experiment outcome is classified from."""

    execution_status: str
    command_status: str | None
    evidence_valid: bool
    baseline_family_digest: str | None
    baseline_signals: tuple[str, ...]
    baseline_time: int | None
    result_family_digest: str | None
    result_signals: tuple[str, ...]
    result_time: int | None
    result_divergence_present: bool
    reduced_stimulus_digest: str | None = None
    artifact_ref: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class OutcomeLabel:
    effect: ObservedEffect
    rationale: str


def classify_observed_effect(evidence: OutcomeEvidence) -> OutcomeLabel:
    """Classify one experiment outcome into a deterministic observed-effect label."""

    ev = evidence

    # An experiment that could not be applied or did not run to completion, or
    # that produced no comparable fingerprint, yields no valid observation.
    if ev.execution_status != "executed":
        return OutcomeLabel(
            ObservedEffect.EXPERIMENT_INVALID,
            f"experiment was not executed (status={ev.execution_status})",
        )
    if ev.command_status in _INVALID_COMMAND_STATUSES:
        return OutcomeLabel(
            ObservedEffect.EXPERIMENT_INVALID,
            f"command did not run to completion (status={ev.command_status})",
        )
    if not ev.evidence_valid or ev.result_family_digest is None:
        return OutcomeLabel(
            ObservedEffect.EXPERIMENT_INVALID,
            "no comparable failure fingerprint was produced for the experiment",
        )

    # The failure no longer reproduces at all.
    if not ev.result_divergence_present or not ev.result_signals:
        return OutcomeLabel(
            ObservedEffect.FAILURE_REMOVED,
            "no divergence reproduced in the intervention run",
        )

    # A divergence is present; compare it against the original failure. Without
    # baseline evidence to compare against, the relationship is ambiguous.
    if not ev.baseline_family_digest or not ev.baseline_signals:
        return OutcomeLabel(
            ObservedEffect.UNKNOWN,
            "a divergence reproduced but the original failure evidence is incomplete",
        )

    shares_signal = bool(set(ev.result_signals) & set(ev.baseline_signals))
    if not shares_signal:
        return OutcomeLabel(
            ObservedEffect.NEW_FAILURE,
            (
                f"divergence on {sorted(ev.result_signals)} differs from the original failing "
                f"signals {sorted(ev.baseline_signals)}"
            ),
        )

    same_family = ev.result_family_digest == ev.baseline_family_digest
    if not same_family:
        return OutcomeLabel(
            ObservedEffect.FAILURE_CHANGED,
            (
                "same failing signal but a materially different failure family "
                f"(result={ev.result_family_digest[:12]}, "
                f"baseline={ev.baseline_family_digest[:12]})"
            ),
        )

    if ev.result_time is not None and ev.baseline_time is not None:
        if ev.result_time > ev.baseline_time:
            return OutcomeLabel(
                ObservedEffect.FAILURE_DELAYED,
                (
                    f"same failure family, later earliest divergence "
                    f"(result t={ev.result_time} > baseline t={ev.baseline_time})"
                ),
            )
        if ev.result_time < ev.baseline_time:
            return OutcomeLabel(
                ObservedEffect.FAILURE_ADVANCED,
                (
                    f"same failure family, earlier earliest divergence "
                    f"(result t={ev.result_time} < baseline t={ev.baseline_time})"
                ),
            )

    return OutcomeLabel(
        ObservedEffect.NO_OBSERVABLE_EFFECT,
        "same failure family, same failing signal, and same earliest divergence time",
    )
