from __future__ import annotations

from rtl_agent.outcome_classification import (
    ObservedEffect,
    OutcomeEvidence,
    classify_observed_effect,
)

_BASE_FAMILY = "fam-original-aaaa"
_BASE_SIGNALS = ("payload_out", "payload_reg")
_BASE_TIME = 40


def _evidence(**overrides: object) -> OutcomeEvidence:
    defaults: dict[str, object] = {
        "execution_status": "executed",
        "command_status": "failed",
        "evidence_valid": True,
        "baseline_family_digest": _BASE_FAMILY,
        "baseline_signals": _BASE_SIGNALS,
        "baseline_time": _BASE_TIME,
        "result_family_digest": _BASE_FAMILY,
        "result_signals": _BASE_SIGNALS,
        "result_time": _BASE_TIME,
        "result_divergence_present": True,
    }
    defaults.update(overrides)
    return OutcomeEvidence(**defaults)  # type: ignore[arg-type]


def _label(**overrides: object) -> ObservedEffect:
    return classify_observed_effect(_evidence(**overrides)).effect


def test_failure_removed_when_no_divergence() -> None:
    assert _label(result_divergence_present=False, result_signals=()) == (
        ObservedEffect.FAILURE_REMOVED
    )


def test_no_observable_effect_same_family_signal_time() -> None:
    assert _label() == ObservedEffect.NO_OBSERVABLE_EFFECT


def test_failure_delayed_later_time() -> None:
    assert _label(result_time=_BASE_TIME + 10) == ObservedEffect.FAILURE_DELAYED


def test_failure_advanced_earlier_time() -> None:
    assert _label(result_time=_BASE_TIME - 10) == ObservedEffect.FAILURE_ADVANCED


def test_failure_changed_same_signal_different_family() -> None:
    assert _label(result_family_digest="fam-different-bbbb") == ObservedEffect.FAILURE_CHANGED


def test_new_failure_disjoint_signal() -> None:
    assert (
        _label(result_signals=("valid_out",), result_family_digest="fam-different-cccc")
        == ObservedEffect.NEW_FAILURE
    )


def test_new_failure_disjoint_signal_even_if_family_matches() -> None:
    # A different failing signal is a new failure regardless of family coincidence.
    assert _label(result_signals=("status_reg",)) == ObservedEffect.NEW_FAILURE


def test_experiment_invalid_not_executed() -> None:
    assert _label(execution_status="invalid") == ObservedEffect.EXPERIMENT_INVALID
    assert _label(execution_status="skipped") == ObservedEffect.EXPERIMENT_INVALID


def test_experiment_invalid_command_did_not_complete() -> None:
    assert _label(command_status="timeout") == ObservedEffect.EXPERIMENT_INVALID
    assert _label(command_status="exec_error") == ObservedEffect.EXPERIMENT_INVALID


def test_experiment_invalid_no_fingerprint() -> None:
    assert _label(evidence_valid=False, result_family_digest=None) == (
        ObservedEffect.EXPERIMENT_INVALID
    )


def test_unknown_when_divergence_but_no_baseline_evidence() -> None:
    assert _label(baseline_family_digest=None, baseline_signals=()) == ObservedEffect.UNKNOWN


def test_no_observable_effect_when_times_unknown_but_family_and_signal_match() -> None:
    assert _label(result_time=None, baseline_time=None) == ObservedEffect.NO_OBSERVABLE_EFFECT


def test_rationale_is_populated_and_auditable() -> None:
    label = classify_observed_effect(_evidence(result_time=_BASE_TIME + 5))
    assert label.effect == ObservedEffect.FAILURE_DELAYED
    assert "later" in label.rationale
    assert str(_BASE_TIME) in label.rationale


def test_classification_is_deterministic() -> None:
    ev = _evidence(result_family_digest="fam-different-dddd")
    first = classify_observed_effect(ev)
    second = classify_observed_effect(ev)
    assert first == second
