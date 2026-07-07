"""Deterministic comparison of one experiment result against the original failure.

Given a single experiment-matrix row — whose baseline fields are the minimized
counterexample reference (validated to share the original failure family) — this
assembles a structured, auditable comparison from the already-computed evidence:
the observed-effect label, the exact/family/canonical fingerprint relationship,
the earliest-divergence-time change, the divergent-signal changes, the
assertion/failure-family changes, the minimized-stimulus relationship, and the
artifact references. It runs no new analysis and makes no causal claim; when the
experiment produced no comparable result fingerprint the comparison is marked
unsupported with the recorded reasons.
"""

from __future__ import annotations

from rtl_agent.experiment_comparison_models import (
    ExperimentComparison,
    FingerprintRelationship,
    SignalChange,
)
from rtl_agent.experiment_matrix_models import MatrixRow


def build_experiment_comparison(
    row: MatrixRow,
    *,
    template_kind: str | None = None,
    confidence: str | None = None,
    minimized_stimulus_digest: str | None = None,
) -> ExperimentComparison:
    has_result_fingerprint = row.result_family_digest is not None
    # "Comparable" means the result reproduced a divergence that can be compared
    # against the original failure. A removed failure (no divergence) and an
    # experiment that produced no fingerprint are both not comparable in that
    # sense, but only the latter is unsupported.
    comparable = row.execution_status == "executed" and bool(row.result_failure_signals)

    exact_match = _both_equal(row.baseline_exact_digest, row.result_exact_digest)
    family_match = _both_equal(row.baseline_family_digest, row.result_family_digest)
    canonical_match = _both_equal(row.baseline_canonical_digest, row.result_canonical_digest)

    family_changed = comparable and not family_match
    canonical_changed = (
        comparable
        and row.baseline_canonical_digest is not None
        and row.result_canonical_digest is not None
        and row.baseline_canonical_digest != row.result_canonical_digest
    )
    assertion_changed = comparable and (
        sorted(row.baseline_assertion_identity) != sorted(row.result_assertion_identity)
    )

    time_change = None
    if row.baseline_failure_time is not None and row.result_failure_time is not None:
        time_change = row.result_failure_time - row.baseline_failure_time

    signal_change = _signal_change(row.baseline_failure_signals, row.result_failure_signals)

    reasons: list[str] = []
    if not has_result_fingerprint:
        reasons = sorted(
            dict.fromkeys(
                row.insufficient_evidence_reasons
                or ["the experiment produced no comparable result fingerprint"]
            )
        )

    comparison = ExperimentComparison(
        intervention_id=row.intervention_id,
        template_kind=template_kind,
        confidence=confidence,
        execution_status=row.execution_status,
        comparable=comparable,
        observed_effect=row.observed_effect,
        observed_effect_rationale=row.observed_effect_rationale,
        fingerprint=FingerprintRelationship(
            relation=row.fingerprint_relation,
            exact_match=exact_match,
            family_match=family_match,
            canonical_match=canonical_match,
        ),
        baseline_exact_digest=row.baseline_exact_digest,
        result_exact_digest=row.result_exact_digest,
        baseline_family_digest=row.baseline_family_digest,
        result_family_digest=row.result_family_digest,
        baseline_canonical_digest=row.baseline_canonical_digest,
        result_canonical_digest=row.result_canonical_digest,
        family_changed=family_changed,
        canonical_changed=canonical_changed,
        assertion_changed=assertion_changed,
        baseline_failure_time=row.baseline_failure_time,
        result_failure_time=row.result_failure_time,
        earliest_divergence_time_change=time_change,
        signal_change=signal_change,
        minimized_stimulus_digest=minimized_stimulus_digest,
        artifact_dir=row.artifact_dir,
        unsupported_reasons=reasons,
    )
    comparison.summary = _summary(comparison)
    return comparison


def _signal_change(baseline: list[str], result: list[str]) -> SignalChange:
    base_set = set(baseline)
    result_set = set(result)
    return SignalChange(
        baseline_signals=sorted(base_set),
        result_signals=sorted(result_set),
        added=sorted(result_set - base_set),
        removed=sorted(base_set - result_set),
        shared=sorted(base_set & result_set),
    )


def _both_equal(left: str | None, right: str | None) -> bool:
    return left is not None and right is not None and left == right


def _summary(c: ExperimentComparison) -> str:
    if c.unsupported_reasons:
        return f"Not comparable to the original failure ({'; '.join(c.unsupported_reasons)})."

    effect = c.observed_effect
    shared = c.signal_change.shared
    delta = c.earliest_divergence_time_change
    if effect == "failure_removed":
        return (
            "The failure no longer reproduced: the result run showed no divergence, so there is "
            "no result fingerprint to compare against the original failure."
        )
    if effect == "no_observable_effect":
        return (
            f"No observable change from the original failure: same divergent signals {shared}, "
            "same failure family, and same earliest divergence time."
        )
    if effect in {"failure_delayed", "failure_advanced"}:
        direction = "later" if (delta or 0) > 0 else "earlier"
        return (
            f"Same failure family on {shared}; earliest divergence moved {direction} by "
            f"{abs(delta) if delta is not None else '?'} time units."
        )
    if effect == "failure_changed":
        return (
            f"Same failing signal(s) {shared}, but the failure family changed "
            f"(family {_p(c.baseline_family_digest)} -> {_p(c.result_family_digest)}, canonical "
            f"{'changed' if c.canonical_changed else 'unchanged'})."
        )
    if effect == "new_failure":
        return (
            f"A different failure appeared: divergent signals changed "
            f"(added {c.signal_change.added}, removed {c.signal_change.removed})."
        )
    return (
        "The relationship to the original failure could not be classified from the available "
        "evidence."
    )


def _p(digest: str | None) -> str:
    return digest[:12] if digest else "-"
