from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ValidationError

from rtl_agent.experiment_matrix import run_experiment_matrix
from rtl_agent.experiment_matrix_models import ExperimentMatrixReport
from rtl_agent.failure_fingerprint import fingerprint_run
from rtl_agent.failure_intelligence_run_models import FailureIntelligenceRunManifest
from rtl_agent.failure_package import export_failure_package
from rtl_agent.failure_report_models import FailureReport
from rtl_agent.intervention_template_models import InterventionTemplateReport
from rtl_agent.intervention_templates import generate_interventions
from rtl_agent.models import utc_now
from rtl_agent.mvp_demo.report import render_demo_markdown, write_demo_summary
from rtl_agent.mvp_demo.synthesis import (
    build_evidence_references,
    build_next_debug_checks,
    build_notable_effects,
)
from rtl_agent.mvp_demo_models import (
    CandidateSummary,
    ExperimentOutcome,
    MinimizationSummary,
    MvpDemoSummary,
    Observation,
    OriginalFailure,
    StageRef,
)
from rtl_agent.reduction import minimize_stimulus
from rtl_agent.reduction_models import StimulusReductionReport
from rtl_agent.run_inspection import inspect_run

_PARSER_NOTES = [
    "The MVP demonstration only sequences the existing failure-intelligence, run-inspection, "
    "failure-package, stimulus-minimization, intervention-template, and experiment-matrix "
    "services; it adds no new analysis behaviour and no parallel path.",
    "Every observation is an observed experimental result. No causal or root-cause claim is "
    "made, and no intervention is applied to the source repository.",
]


class MvpDemoError(RuntimeError):
    pass


def run_mvp_demo(
    *,
    failure_run: Path,
    repo: Path,
    config_path: Path,
    command: str,
    stimulus: Path,
    allowed_files: list[str],
    output: Path,
    max_candidates: int = 8,
    max_experiments: int = 12,
    timeout: int | None = None,
    baseline_commit: str | None = None,
) -> MvpDemoSummary:
    """Run the full failing-regression-to-summary demonstration (composition only)."""

    output_dir = output.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise MvpDemoError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    stages: list[StageRef] = []
    warnings: list[str] = []

    # Stage 1-2: the failing regression is represented by an existing failure run;
    # inspect it before anything downstream trusts its evidence.
    inspection = inspect_run(failure_run.resolve())
    if not inspection.valid:
        raise MvpDemoError(
            f"refusing to demonstrate on an invalid failure run: {failure_run} "
            f"(status={inspection.manifest_status})"
        )
    stages.append(
        StageRef(
            stage="inspect-run",
            status="valid",
            reference=str(failure_run.resolve()),
            detail=f"{inspection.valid_artifacts} artifacts verified",
        )
    )

    original = _original_failure(failure_run.resolve())

    # Stage 3: export a portable failure package.
    package_dir = output_dir / "failure-package"
    package = export_failure_package(failure_run.resolve(), package_dir)
    original.failure_package = str(package_dir)
    original.failure_package_files = package.file_count
    stages.append(
        StageRef(
            stage="export-failure-package",
            status=str(package.package_status),
            reference=str(package_dir),
            detail=f"{package.file_count} files",
        )
    )

    # Stage 4: minimize the failing stimulus to a counterexample.
    reduction = minimize_stimulus(
        baseline_run=failure_run,
        repo=repo,
        config_path=config_path,
        command=command,
        stimulus_path=stimulus,
        output=output_dir / "minimization",
        timeout=timeout,
        baseline_commit=baseline_commit,
    )
    reduction_report_path = output_dir / "minimization" / "reduction-report.json"
    minimization = _minimization_summary(reduction, reduction_report_path)
    stages.append(
        StageRef(
            stage="minimize-stimulus",
            status=str(reduction.final_classification),
            reference=str(reduction_report_path),
            detail=(f"{reduction.original_item_count} -> {reduction.minimized_item_count} items"),
        )
    )

    # Stage 5: generate reviewable intervention candidates from the evidence.
    generated = generate_interventions(
        failure_run=failure_run,
        repo=repo,
        allowed_files=allowed_files,
        output=output_dir / "generated",
        max_candidates=max_candidates,
        reduction_report=reduction_report_path,
        baseline_commit=baseline_commit,
    )
    candidates = _candidate_summaries(generated)
    stages.append(
        StageRef(
            stage="generate-interventions",
            status="generated",
            reference=str(output_dir / "generated" / "interventions.json"),
            detail=f"{len(candidates)} candidates",
        )
    )

    # Stage 6: run the experiment matrix against the generated manifest.
    matrix: ExperimentMatrixReport | None = None
    outcomes: list[ExperimentOutcome] = []
    if candidates:
        matrix = run_experiment_matrix(
            baseline_run=failure_run,
            reduction_report=reduction_report_path,
            repo=repo,
            config_path=config_path,
            command=command,
            interventions=output_dir / "generated" / "interventions.json",
            output=output_dir / "matrix",
            max_experiments=max_experiments,
            timeout=timeout,
            baseline_commit=baseline_commit,
        )
        outcomes = _outcomes(matrix, generated)
        stages.append(
            StageRef(
                stage="run-experiment-matrix",
                status="executed",
                reference=str(output_dir / "matrix" / "experiment-matrix.json"),
                detail=f"{matrix.summary.executed} experiments executed",
            )
        )
        warnings.extend(matrix.warnings)
    else:
        stages.append(
            StageRef(
                stage="run-experiment-matrix",
                status="skipped",
                detail="no reviewable candidate was generated to experiment with",
            )
        )

    summary = MvpDemoSummary(
        demo_id=output_dir.name,
        created_at=utc_now(),
        target_repo=str(repo.resolve()),
        target_commit=matrix.target_commit if matrix else generated.target_commit,
        command_name=command,
        stages=stages,
        original_failure=original,
        minimization=minimization,
        generated_candidates=candidates,
        candidate_counts=_candidate_counts(candidates),
        experiment_outcomes=outcomes,
        outcome_counts=_outcome_counts(matrix),
        observed_effect_counts=_observed_effect_counts(outcomes),
        observations=_observations(original, minimization, candidates, outcomes),
        notable_effects=build_notable_effects(outcomes),
        evidence_references=build_evidence_references(stages, original, minimization, outcomes),
        next_debug_checks=build_next_debug_checks(minimization, outcomes, candidates),
        warnings=sorted(dict.fromkeys(warnings)),
        parser_notes=_PARSER_NOTES,
    )

    write_demo_summary(summary, output_dir / "mvp-demo-summary.json")
    render_demo_markdown(summary, output_dir / "mvp-demo-summary.md")
    return summary


def _original_failure(failure_run: Path) -> OriginalFailure:
    fingerprint = fingerprint_run(failure_run)
    manifest = _read(failure_run / "run-manifest.json", FailureIntelligenceRunManifest)
    report_path = failure_run / (manifest.failure_report_path or "failure-report.json")
    report = _read(report_path, FailureReport)
    signals = list(report.earliest_divergence_signals)
    return OriginalFailure(
        failure_run=str(failure_run),
        run_valid=True,
        manifest_status=str(manifest.status),
        family_digest=fingerprint.family_digest,
        exact_digest=fingerprint.exact_digest,
        earliest_divergence_time=report.earliest_divergence_time,
        earliest_divergence_signals=signals,
    )


def _minimization_summary(
    reduction: StimulusReductionReport, report_path: Path
) -> MinimizationSummary:
    original = reduction.original_item_count
    minimized = reduction.minimized_item_count
    percent = round(100 * (original - minimized) / original) if original else 0
    return MinimizationSummary(
        reduction_report=str(report_path),
        original_item_count=original,
        minimized_item_count=minimized,
        percent_reduced=percent,
        final_classification=str(reduction.final_classification),
        minimized_stimulus_digest=reduction.minimized_stimulus_digest,
    )


def _candidate_summaries(report: InterventionTemplateReport) -> list[CandidateSummary]:
    return [
        CandidateSummary(
            candidate_id=c.candidate_id,
            template_kind=str(c.template_kind),
            confidence=str(c.confidence),
            file=c.file,
            source_line=c.source_line,
            affected_signal=c.affected_signal,
            hypothesis=c.hypothesis,
        )
        for c in report.candidates
    ]


def _candidate_counts(candidates: list[CandidateSummary]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        counts[candidate.confidence] = counts.get(candidate.confidence, 0) + 1
    return counts


def _outcomes(
    matrix: ExperimentMatrixReport, generated: InterventionTemplateReport
) -> list[ExperimentOutcome]:
    kind_by_id = {c.candidate_id: str(c.template_kind) for c in generated.candidates}
    conf_by_id = {c.candidate_id: str(c.confidence) for c in generated.candidates}
    outcomes: list[ExperimentOutcome] = []
    for row in matrix.rows:
        outcomes.append(
            ExperimentOutcome(
                intervention_id=row.intervention_id,
                template_kind=kind_by_id.get(row.intervention_id),
                confidence=conf_by_id.get(row.intervention_id),
                execution_status=row.execution_status,
                observed_effect=row.observed_effect,
                observed_effect_rationale=row.observed_effect_rationale,
                counterfactual_outcome=row.counterfactual_outcome,
                fingerprint_relation=row.fingerprint_relation,
                failure_removed=row.failure_removed,
                different_failure=row.different_failure,
                family_preserved=row.family_preserved,
                failure_time_shifted=row.failure_time_shifted,
                result_family_digest=row.result_family_digest,
                artifact_dir=row.artifact_dir,
            )
        )
    return outcomes


def _outcome_counts(matrix: ExperimentMatrixReport | None) -> dict[str, int]:
    if matrix is None:
        return {}
    s = matrix.summary
    return {
        "executed": s.executed,
        "failures_removed": s.failures_removed,
        "changed_family": s.changed_family,
        "no_effect": s.no_effect,
        "same_family": s.same_family,
        "insufficient_evidence": s.insufficient_evidence,
    }


def _observations(
    original: OriginalFailure,
    minimization: MinimizationSummary,
    candidates: list[CandidateSummary],
    outcomes: list[ExperimentOutcome],
) -> list[Observation]:
    observations: list[Observation] = []
    family = (original.family_digest or "")[:12]
    observations.append(
        Observation(
            category="original_failure",
            statement=(
                f"The baseline run reproduces an observed failure family `{family}` with earliest "
                f"divergence on {original.earliest_divergence_signals} at "
                f"t={original.earliest_divergence_time}."
            ),
        )
    )
    observations.append(
        Observation(
            category="minimization",
            statement=(
                f"The failing stimulus was reduced from {minimization.original_item_count} to "
                f"{minimization.minimized_item_count} items ({minimization.percent_reduced}% "
                f"smaller) while preserving the failure family "
                f"({minimization.final_classification})."
            ),
        )
    )
    hypothesis_by_id = {c.candidate_id: c.hypothesis for c in candidates}
    for outcome in outcomes:
        phrase = _effect_phrase(outcome.observed_effect)
        where = hypothesis_by_id.get(outcome.intervention_id, outcome.intervention_id)
        observations.append(
            Observation(
                intervention_id=outcome.intervention_id,
                category="experiment_result",
                statement=(
                    f"Experiment `{outcome.intervention_id}` ({outcome.template_kind}, "
                    f"{outcome.confidence}) → observed effect `{outcome.observed_effect}`: "
                    f"{phrase}. Hypothesis under test: {where}"
                ),
            )
        )
    if not outcomes:
        observations.append(
            Observation(
                category="experiment_result",
                statement="No generated experiment produced a measurable change in the failure.",
            )
        )
    return observations


_EFFECT_PHRASES = {
    "failure_removed": "the observed failure no longer reproduced",
    "failure_delayed": "the same observed failure reproduced later in time",
    "failure_advanced": "the same observed failure reproduced earlier in time",
    "failure_changed": "the same signal produced a materially different observed failure",
    "no_observable_effect": "no observable change in the failure was measured",
    "new_failure": "a different observed failure appeared on another signal",
    "experiment_invalid": "the experiment did not produce a comparable observation",
    "unknown": "the observed effect could not be classified deterministically",
}


def _effect_phrase(effect: str) -> str:
    return _EFFECT_PHRASES.get(effect, "the observed effect could not be classified")


def _observed_effect_counts(outcomes: list[ExperimentOutcome]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.observed_effect] = counts.get(outcome.observed_effect, 0) + 1
    return dict(sorted(counts.items()))


def _read[ModelT: BaseModel](path: Path, model: type[ModelT]) -> ModelT:
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise MvpDemoError(f"required artifact is unreadable: {path} ({exc})") from exc
