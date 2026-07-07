from __future__ import annotations

from datetime import UTC, datetime

from rtl_agent.mvp_demo.synthesis import (
    build_evidence_references,
    build_next_debug_checks,
    build_notable_effects,
    render_debug_summary,
)
from rtl_agent.mvp_demo_models import (
    CandidateSummary,
    ExperimentOutcome,
    MinimizationSummary,
    MvpDemoSummary,
    OriginalFailure,
    StageRef,
)
from rtl_agent.repair_suggestions import RepairSuggestion

_MINIMIZATION = MinimizationSummary(
    reduction_report="/out/minimization/reduction-report.json",
    original_item_count=7,
    minimized_item_count=3,
    percent_reduced=57,
    final_classification="same_failure_family",
    minimized_stimulus_digest="d" * 64,
)


def _candidate(cid: str, kind: str, line: int) -> CandidateSummary:
    return CandidateSummary(
        candidate_id=cid,
        template_kind=kind,
        confidence="high_evidence",
        file="rtl/core.sv",
        source_line=line,
        affected_signal="hold",
        hypothesis=f"does {cid} contribute?",
    )


def _outcome(cid: str, kind: str, effect: str, **kw: object) -> ExperimentOutcome:
    defaults: dict[str, object] = {
        "intervention_id": cid,
        "template_kind": kind,
        "confidence": "high_evidence",
        "execution_status": "executed" if effect != "experiment_invalid" else "invalid",
        "observed_effect": effect,
        "observed_effect_rationale": f"rationale for {effect}",
        "artifact_dir": f"rows/{cid}",
    }
    defaults.update(kw)
    return ExperimentOutcome(**defaults)  # type: ignore[arg-type]


_STAGES = [
    StageRef(stage="inspect-run", status="valid", reference="/out/run"),
    StageRef(stage="generate-interventions", status="generated", reference="/out/gen.json"),
    StageRef(stage="run-experiment-matrix", status="executed", reference="/out/matrix.json"),
]

_ORIGINAL = OriginalFailure(
    failure_run="/out/run",
    run_valid=True,
    family_digest="f" * 64,
    earliest_divergence_time=65,
    earliest_divergence_signals=["hold"],
    failure_package="/out/failure-package",
    failure_package_files=13,
)


def _summary(
    outcomes: list[ExperimentOutcome], candidates: list[CandidateSummary]
) -> MvpDemoSummary:
    return MvpDemoSummary(
        demo_id="demo",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        target_repo="/repo",
        target_commit="abc123",
        command_name="sim",
        stages=_STAGES,
        original_failure=_ORIGINAL,
        minimization=_MINIMIZATION,
        generated_candidates=candidates,
        candidate_counts={"high_evidence": len(candidates)},
        experiment_outcomes=outcomes,
        observed_effect_counts=_effect_counts(outcomes),
        notable_effects=build_notable_effects(outcomes),
        evidence_references=build_evidence_references(_STAGES, _ORIGINAL, _MINIMIZATION, outcomes),
        next_debug_checks=build_next_debug_checks(_MINIMIZATION, outcomes, candidates),
    )


def _effect_counts(outcomes: list[ExperimentOutcome]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for o in outcomes:
        counts[o.observed_effect] = counts.get(o.observed_effect, 0) + 1
    return counts


def test_notable_effects_grouped_and_ordered() -> None:
    outcomes = [
        _outcome("c-noeffect", "suppress_assignment", "no_observable_effect"),
        _outcome("a-removed", "hold_register", "failure_removed"),
        _outcome("b-removed", "override_condition", "failure_removed"),
        _outcome("d-changed", "suppress_assignment", "failure_changed"),
    ]
    groups = build_notable_effects(outcomes)
    # Ordered by the fixed label priority, not insertion or alphabetical order.
    assert [g.label for g in groups] == [
        "failure_removed",
        "failure_changed",
        "no_observable_effect",
    ]
    removed = groups[0]
    assert removed.count == 2
    # Interventions within a group are sorted deterministically.
    assert removed.interventions == ["a-removed", "b-removed"]


def test_next_debug_checks_are_observation_based_and_deterministic() -> None:
    outcomes = [
        _outcome("rm", "hold_register", "failure_removed"),
        _outcome("ch", "suppress_assignment", "failure_changed"),
        _outcome("nf", "suppress_assignment", "new_failure"),
        _outcome("iv", "hold_register", "experiment_invalid"),
    ]
    candidates = [_candidate(o.intervention_id, o.template_kind or "x", 34) for o in outcomes]
    checks_a = build_next_debug_checks(_MINIMIZATION, outcomes, candidates)
    checks_b = build_next_debug_checks(_MINIMIZATION, outcomes, candidates)
    assert [c.statement for c in checks_a] == [c.statement for c in checks_b]
    assert [c.priority for c in checks_a] == list(range(1, len(checks_a) + 1))

    text = " ".join(c.statement for c in checks_a).lower()
    # Observation-based verbs only; never a causal claim.
    assert "inspect" in text or "compare" in text or "check" in text
    assert "caused by" not in text
    assert "root cause" not in text
    # The minimized reproducer is always suggested last.
    assert "compact reproducer" in checks_a[-1].statement


def test_next_debug_checks_when_no_effect() -> None:
    outcomes = [_outcome("n1", "hold_register", "no_observable_effect")]
    candidates = [_candidate("n1", "hold_register", 34)]
    checks = build_next_debug_checks(_MINIMIZATION, outcomes, candidates)
    joined = " ".join(c.statement for c in checks)
    assert "No generated edit altered the observed failure" in joined


def test_render_debug_summary_has_all_sections_in_order() -> None:
    outcomes = [
        _outcome("a-removed", "hold_register", "failure_removed"),
        _outcome("d-changed", "suppress_assignment", "failure_changed"),
    ]
    candidates = [_candidate("a-removed", "hold_register", 34), _candidate("d-changed", "x", 22)]
    summary = _summary(outcomes, candidates)
    markdown = render_debug_summary(summary)

    required = [
        "# Counterfactual debug summary",
        "## Original failure",
        "## Minimized stimulus",
        "## Generated interventions",
        "## Outcome classification",
        "## Notable observed effects",
        "## Evidence references",
        "## Next debug checks",
        "## Disclaimer",
    ]
    positions = [markdown.find(heading) for heading in required]
    assert all(pos >= 0 for pos in positions), positions
    assert positions == sorted(positions), "sections must appear in the documented order"

    # Grouped observed effects with source locations and the label rationale.
    assert "### `failure_removed` (1)" in markdown
    assert "`rtl/core.sv:34`" in markdown
    assert "rationale for failure_removed" in markdown
    # Evidence references and next checks are present.
    assert "- run-experiment-matrix: `/out/matrix.json`" in markdown
    assert "1. Inspect the edit sites" in markdown
    # No affirmative causal language (the disclaimer may deny root cause).
    assert "caused by" not in markdown.lower()
    assert "root cause of" not in markdown.lower()
    assert "does not establish causality" in markdown


def test_render_is_deterministic() -> None:
    outcomes = [_outcome("a-removed", "hold_register", "failure_removed")]
    candidates = [_candidate("a-removed", "hold_register", 34)]
    summary = _summary(outcomes, candidates)
    assert render_debug_summary(summary) == render_debug_summary(summary)


def test_render_debug_summary_surfaces_repair_suggestions() -> None:
    outcomes = [_outcome("a-removed", "hold_register", "failure_removed")]
    candidates = [_candidate("a-removed", "hold_register", 34)]
    summary = _summary(outcomes, candidates)
    summary.repair_suggestions = [
        RepairSuggestion(
            suggestion_id="repair-suggestion:a-removed",
            suggested_area="Inspect `rtl/core.sv:34` and related signal `hold`.",
            evidence_basis=["intervention `a-removed` observed `failure_removed`"],
            related_source_locations=["rtl/core.sv:34"],
            related_signals=["hold"],
            supporting_interventions=["a-removed"],
            supporting_outcomes=["failure_removed"],
            confidence="high_evidence",
        )
    ]

    markdown = render_debug_summary(summary)

    assert "## Repair-direction suggestions" in markdown
    assert "`repair-suggestion:a-removed`" in markdown
    assert "not patches or root-cause claims" in markdown
    assert "intervention `a-removed` observed `failure_removed`" in markdown


def test_unknown_and_invalid_labels_are_surfaced() -> None:
    outcomes = [
        _outcome("u1", "suppress_assignment", "unknown"),
        _outcome("i1", "hold_register", "experiment_invalid"),
    ]
    candidates = [_candidate("u1", "x", 10), _candidate("i1", "y", 12)]
    summary = _summary(outcomes, candidates)
    markdown = render_debug_summary(summary)
    assert "### `experiment_invalid`" in markdown
    assert "### `unknown`" in markdown
    checks = " ".join(c.statement for c in summary.next_debug_checks)
    assert "could not be classified" in checks
    assert "did not complete" in checks
