from __future__ import annotations

from rtl_agent.counterfactual_models import CounterfactualOutcome, FailureIdentity

# Command statuses (from CommandStatus) that mean the experiment never produced a
# comparable run and cannot be classified as an intervention effect.
_INFRA_FAILURE_STATUSES = frozenset({"timeout", "exec_error"})


def classify_outcome(
    *,
    command_status: str,
    intervention_evidence_valid: bool,
    baseline: FailureIdentity,
    intervention: FailureIdentity,
) -> tuple[CounterfactualOutcome, list[str]]:
    """Deterministically classify a counterfactual outcome from explicit evidence.

    Classification is based only on: whether the command ran to completion, whether
    valid intervention waveform/comparison evidence exists, the baseline and
    intervention divergent-signal sets, and their failure timestamps. It never
    infers causality.
    """

    if command_status in _INFRA_FAILURE_STATUSES:
        return (
            CounterfactualOutcome.EXPERIMENT_FAILED,
            [f"intervention command did not run to completion (status: {command_status})"],
        )
    if not intervention_evidence_valid:
        return (
            CounterfactualOutcome.INSUFFICIENT_EVIDENCE,
            ["no valid intervention waveform or comparison evidence was produced"],
        )
    if not baseline.divergence_present:
        return (
            CounterfactualOutcome.INSUFFICIENT_EVIDENCE,
            ["baseline run records no localized divergence to compare against"],
        )

    baseline_signals = set(baseline.signals)
    intervention_signals = set(intervention.signals)

    if not intervention.divergence_present:
        return CounterfactualOutcome.FAILURE_REMOVED, []

    if intervention_signals == baseline_signals:
        if baseline.failure_time is None or intervention.failure_time is None:
            return (
                CounterfactualOutcome.INSUFFICIENT_EVIDENCE,
                ["a divergence timestamp is missing, so timing change cannot be classified"],
            )
        if intervention.failure_time < baseline.failure_time:
            return CounterfactualOutcome.FAILURE_ADVANCED, []
        if intervention.failure_time > baseline.failure_time:
            return CounterfactualOutcome.FAILURE_DELAYED, []
        return CounterfactualOutcome.NO_OBSERVABLE_EFFECT, []

    if baseline_signals & intervention_signals:
        return CounterfactualOutcome.FAILURE_CHANGED, []

    return CounterfactualOutcome.NEW_FAILURE_INTRODUCED, []
