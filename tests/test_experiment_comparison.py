from __future__ import annotations

from rtl_agent.experiment_comparison import build_experiment_comparison
from rtl_agent.experiment_matrix_models import MatrixRow

_BASELINE = {
    "baseline_exact_digest": "exact-base",
    "baseline_family_digest": "fam-base",
    "baseline_canonical_digest": "canon-base",
    "baseline_failure_signals": ["payload_out", "payload_reg"],
    "baseline_failure_time": 40,
    "baseline_assertion_identity": ["payload_stable|failed"],
}


def _row(**overrides: object) -> MatrixRow:
    data: dict[str, object] = {
        "intervention_id": "cand-1",
        "intervention_digest": "d",
        "experiment_digest": "e",
        "execution_status": "executed",
        **_BASELINE,
    }
    data.update(overrides)
    return MatrixRow(**data)  # type: ignore[arg-type]


def _cmp(**overrides: object):  # type: ignore[no-untyped-def]
    return build_experiment_comparison(
        _row(**overrides),
        template_kind="hold_register",
        confidence="high_evidence",
        minimized_stimulus_digest="stim-digest",
    )


def test_no_observable_effect_comparison() -> None:
    c = _cmp(
        observed_effect="no_observable_effect",
        result_exact_digest="exact-base",
        result_family_digest="fam-base",
        result_canonical_digest="canon-base",
        result_failure_signals=["payload_out", "payload_reg"],
        result_failure_time=40,
        result_assertion_identity=["payload_stable|failed"],
        fingerprint_relation="exact",
    )
    assert c.comparable is True
    assert (
        c.fingerprint.exact_match and c.fingerprint.family_match and c.fingerprint.canonical_match
    )
    assert c.family_changed is False and c.canonical_changed is False
    assert c.assertion_changed is False
    assert c.earliest_divergence_time_change == 0
    assert c.signal_change.added == [] and c.signal_change.removed == []
    assert "No observable change" in c.summary


def test_failure_changed_comparison() -> None:
    c = _cmp(
        observed_effect="failure_changed",
        result_exact_digest="exact-x",
        result_family_digest="fam-x",
        result_canonical_digest="canon-x",
        result_failure_signals=["payload_out", "payload_reg"],
        result_failure_time=40,
        fingerprint_relation="related_but_materially_different_failure",
    )
    assert c.family_changed is True
    assert c.canonical_changed is True
    assert c.fingerprint.family_match is False
    assert c.signal_change.shared == ["payload_out", "payload_reg"]
    assert "failure family changed" in c.summary


def test_failure_removed_comparison() -> None:
    # A removed failure produces a (no-divergence) fingerprint but no failing
    # signals: not comparable as a failure, and not flagged as changed.
    c = _cmp(
        observed_effect="failure_removed",
        result_exact_digest="exact-none",
        result_family_digest="fam-none",
        result_canonical_digest="canon-none",
        result_failure_signals=[],
        failure_removed=True,
    )
    assert c.comparable is False
    assert c.unsupported_reasons == []
    assert c.family_changed is False and c.canonical_changed is False
    assert c.signal_change.removed == ["payload_out", "payload_reg"]
    assert "no longer reproduced" in c.summary


def test_new_failure_comparison() -> None:
    c = _cmp(
        observed_effect="new_failure",
        result_exact_digest="exact-n",
        result_family_digest="fam-n",
        result_canonical_digest="canon-n",
        result_failure_signals=["valid_out"],
        result_failure_time=30,
        different_failure=True,
    )
    assert c.signal_change.added == ["valid_out"]
    assert set(c.signal_change.removed) == {"payload_out", "payload_reg"}
    assert c.earliest_divergence_time_change == -10
    assert "different failure appeared" in c.summary


def test_timing_shift_comparison() -> None:
    c = _cmp(
        observed_effect="failure_delayed",
        result_exact_digest="exact-t",
        result_family_digest="fam-base",
        result_canonical_digest="canon-base",
        result_failure_signals=["payload_out", "payload_reg"],
        result_failure_time=60,
        failure_time_shifted=True,
    )
    assert c.earliest_divergence_time_change == 20
    assert "moved later by 20" in c.summary


def test_invalid_experiment_is_unsupported() -> None:
    c = _cmp(
        observed_effect="experiment_invalid",
        execution_status="executed",
        command_status="failed",
        result_family_digest=None,
        result_failure_signals=[],
        insufficient_evidence_reasons=["command did not run to completion"],
    )
    assert c.comparable is False
    assert c.unsupported_reasons == ["command did not run to completion"]
    assert "Not comparable" in c.summary


def test_comparison_is_deterministic() -> None:
    row = _row(
        observed_effect="failure_changed",
        result_family_digest="fam-x",
        result_canonical_digest="canon-x",
        result_failure_signals=["payload_reg", "payload_out"],
        result_failure_time=40,
    )
    a = build_experiment_comparison(row, minimized_stimulus_digest="s")
    b = build_experiment_comparison(row, minimized_stimulus_digest="s")
    assert a.model_dump() == b.model_dump()
    # Signal lists are deterministically sorted regardless of input order.
    assert a.signal_change.shared == ["payload_out", "payload_reg"]
