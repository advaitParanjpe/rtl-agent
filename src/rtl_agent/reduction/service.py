from __future__ import annotations

import subprocess
from pathlib import Path

from pydantic import ValidationError

from rtl_agent.artifacts import RunStore
from rtl_agent.config import AgentConfig, load_config
from rtl_agent.failure_fingerprint import fingerprint_run
from rtl_agent.failure_intelligence_run_models import FailureIntelligenceRunManifest
from rtl_agent.git.worktree import GitWorktreeError, GitWorktreeManager
from rtl_agent.models import utc_now
from rtl_agent.reduction.ddmin import BudgetExhausted, ddmin
from rtl_agent.reduction.evaluate import (
    BaselineFingerprint,
    EvaluationContext,
    evaluate_candidate,
)
from rtl_agent.reduction.report import render_reduction_markdown, write_reduction_report
from rtl_agent.reduction_models import (
    CandidateEvaluation,
    PreservationClass,
    SimulatorResultSummary,
    StimulusReductionReport,
    TerminationReason,
)
from rtl_agent.run_inspection import RunInspectionError, inspect_run
from rtl_agent.stimulus import parse_stimulus, stimulus_digest, subset_by_ids
from rtl_agent.stimulus_models import StructuredStimulus

_PARSER_NOTES = [
    "Stimulus minimization reuses the existing command runner, Git worktree isolation, triage, "
    "failure-intelligence orchestration, and fingerprint services; it adds no parallel analysis "
    "path and mutates no source repository.",
    "Reduction removes only whole stimulus items and preserves the relative order of retained "
    "items. Preservation is judged solely by the failure-fingerprint family digest; it is not a "
    "minimality or causality claim.",
]


class StimulusReductionError(RuntimeError):
    pass


def minimize_stimulus(
    *,
    baseline_run: Path,
    repo: Path,
    config_path: Path,
    command: str,
    stimulus_path: Path,
    output: Path,
    max_evaluations: int = 32,
    timeout: int | None = None,
    baseline_commit: str | None = None,
) -> StimulusReductionReport:
    """Minimize a structured failing stimulus while preserving the failure family."""

    if max_evaluations < 1:
        raise StimulusReductionError("max evaluations must be at least 1")

    source_repo = repo.resolve()
    config = _load_config(config_path)
    if command not in config.commands:
        raise StimulusReductionError(f"unknown command: {command} (not in {config_path})")
    if timeout is not None:
        config = _with_timeout(config, command, timeout)

    baseline, baseline_run_dir = _load_baseline(baseline_run)
    original = _load_stimulus(stimulus_path)
    original_ids = [item.id for item in original.items]

    store = RunStore(output.resolve().parent, run_id=output.resolve().name)
    if store.run_dir.exists() and any(store.run_dir.iterdir()):
        raise StimulusReductionError(f"output directory is not empty: {store.run_dir}")
    store.create()
    experiment_dir = store.run_dir

    manager = GitWorktreeManager(source_repo, experiment_dir)
    try:
        manager.validate_source_repo()
    except GitWorktreeError as exc:
        raise StimulusReductionError(str(exc)) from exc
    resolved_commit = _resolve_commit(source_repo, baseline_commit)

    warnings: list[str] = []
    history: list[CandidateEvaluation] = []
    cache: dict[str, CandidateEvaluation] = {}
    simulator_result: SimulatorResultSummary | None = None
    unique_evaluations = 0
    cache_hits = 0

    plan = manager.create("minimize", ref=resolved_commit)
    context = EvaluationContext(
        worktree_path=plan.worktree_path,
        config=config,
        command=command,
        repository_root=_worktree_repo_root(plan.worktree_path, config),
        candidates_root=experiment_dir / "candidates",
        baseline=baseline,
    )

    def evaluate(retained_ids: list[str]) -> CandidateEvaluation:
        nonlocal unique_evaluations, cache_hits, simulator_result
        digest = stimulus_digest(subset_by_ids(original, retained_ids))
        if digest in cache:
            cache_hits += 1
            cached = cache[digest].model_copy(update={"from_cache": True})
            history.append(cached)
            return cache[digest]
        if unique_evaluations >= max_evaluations:
            raise BudgetExhausted
        evaluation, summary = evaluate_candidate(context, original, retained_ids)
        if simulator_result is None:
            simulator_result = summary
        unique_evaluations += 1
        cache[digest] = evaluation
        history.append(evaluation)
        return evaluation

    def oracle(retained_ids: list[str]) -> bool:
        return evaluate(retained_ids).preserves

    try:
        baseline_preserved = evaluate(original_ids)
        if not baseline_preserved.preserves:
            retained_ids = original_ids
            termination = TerminationReason.BASELINE_NOT_PRESERVED
            warnings.append(
                "the original stimulus did not reproduce the baseline failure family in the "
                f"worktree (classified {baseline_preserved.classification}); no reduction performed"
            )
        elif len(original_ids) < 2:
            retained_ids = original_ids
            termination = TerminationReason.ALREADY_MINIMAL
        else:
            try:
                retained_ids, termination = ddmin(original_ids, oracle)
            except BudgetExhausted:
                retained_ids, termination = original_ids, TerminationReason.BUDGET_EXHAUSTED
    finally:
        _remove_worktree(manager, plan.worktree_path, warnings)

    minimized = subset_by_ids(original, retained_ids)
    minimized_digest = stimulus_digest(minimized)
    final = cache.get(minimized_digest)
    final_classification = (
        final.classification if final else PreservationClass.INSUFFICIENT_EVIDENCE
    )
    insufficient_reasons = (
        [str(final.detail)] if final and final.detail and not final.preserves else []
    )

    original_stim_path = experiment_dir / "original-stimulus.json"
    minimized_stim_path = experiment_dir / "minimized-stimulus.json"
    _write_stimulus(original, original_stim_path)
    _write_stimulus(minimized, minimized_stim_path)

    report = StimulusReductionReport(
        minimization_id=store.run_id,
        created_at=utc_now(),
        baseline_run=str(baseline_run_dir),
        baseline_fingerprint_exact_digest=baseline.exact_digest,
        baseline_fingerprint_family_digest=baseline.family_digest,
        target_repo=str(source_repo),
        target_commit=resolved_commit,
        command_name=command,
        original_stimulus=original_stim_path.relative_to(experiment_dir).as_posix(),
        original_stimulus_digest=stimulus_digest(original),
        minimized_stimulus=minimized_stim_path.relative_to(experiment_dir).as_posix(),
        minimized_stimulus_digest=minimized_digest,
        original_item_count=len(original.items),
        minimized_item_count=len(minimized.items),
        retained_item_ids=[item.id for item in minimized.items],
        removed_item_ids=[item_id for item_id in original_ids if item_id not in set(retained_ids)],
        final_classification=final_classification,
        total_evaluations=unique_evaluations,
        cache_hits=cache_hits,
        evaluation_budget=max_evaluations,
        termination_reason=termination,
        evaluation_history=history,
        simulator_result=simulator_result,
        reproducibility_instructions=_reproducibility_instructions(command),
        warnings=sorted(dict.fromkeys(warnings)),
        insufficient_evidence_reasons=sorted(dict.fromkeys(insufficient_reasons)),
        parser_notes=_PARSER_NOTES,
    )
    write_reduction_report(report, experiment_dir / "reduction-report.json")
    render_reduction_markdown(report, experiment_dir / "reduction-report.md")
    store.append_event("stimulus_minimization", {"classification": str(final_classification)})
    return report


def _load_config(config_path: Path) -> AgentConfig:
    try:
        return load_config(config_path)
    except ValueError as exc:
        raise StimulusReductionError(str(exc)) from exc


def _with_timeout(config: AgentConfig, command: str, timeout: int) -> AgentConfig:
    spec = config.commands[command].model_copy(update={"timeout_seconds": timeout})
    commands = dict(config.commands)
    commands[command] = spec
    return config.model_copy(update={"commands": commands})


def _load_baseline(baseline_run: Path) -> tuple[BaselineFingerprint, Path]:
    resolved = baseline_run.resolve()
    try:
        inspection = inspect_run(resolved)
    except RunInspectionError as exc:
        raise StimulusReductionError(f"baseline run could not be inspected: {exc}") from exc
    if not inspection.valid:
        raise StimulusReductionError(
            f"refusing to use an invalid baseline run: {resolved} "
            f"(status={inspection.manifest_status})"
        )
    manifest_path = resolved / "run-manifest.json"
    try:
        manifest = FailureIntelligenceRunManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError, ValueError) as exc:
        raise StimulusReductionError(
            f"baseline run manifest is unreadable: {manifest_path}"
        ) from exc
    fingerprint = fingerprint_run(resolved)
    if fingerprint.insufficient_evidence:
        raise StimulusReductionError(
            "baseline fingerprint has insufficient evidence to anchor a failure family"
        )
    baseline = BaselineFingerprint(
        exact_digest=fingerprint.exact_digest,
        family_digest=fingerprint.family_digest,
        failure_time=manifest.failure_time,
        before=manifest.before,
        after=manifest.after,
    )
    return baseline, resolved


def _load_stimulus(stimulus_path: Path) -> StructuredStimulus:
    from rtl_agent.stimulus import StimulusError

    try:
        return parse_stimulus(stimulus_path)
    except StimulusError as exc:
        raise StimulusReductionError(str(exc)) from exc


def _worktree_repo_root(worktree_path: Path, config: AgentConfig) -> Path:
    repository_path = config.repository_path
    if repository_path.is_absolute():
        return worktree_path
    return (worktree_path / repository_path).resolve()


def _resolve_commit(source_repo: Path, baseline_commit: str | None) -> str:
    ref = baseline_commit or "HEAD"
    result = subprocess.run(
        ["git", "-C", str(source_repo), "rev-parse", ref],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise StimulusReductionError(
            f"could not resolve commit '{ref}' in {source_repo}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _remove_worktree(manager: GitWorktreeManager, worktree_path: Path, warnings: list[str]) -> None:
    try:
        manager.remove(worktree_path)
    except GitWorktreeError as exc:
        warnings.append(f"worktree cleanup did not complete: {exc}")


def _write_stimulus(stimulus: StructuredStimulus, output: Path) -> None:
    from rtl_agent.stimulus import write_stimulus

    write_stimulus(stimulus, output)


def _reproducibility_instructions(command: str) -> list[str]:
    return [
        "The minimized stimulus is saved as minimized-stimulus.json in this experiment directory.",
        f"To reproduce, materialize it into the repository's sim/stimulus.mem and run the "
        f"configured '{command}' command; the failure family classification is recorded above.",
        "Every evaluated candidate's artifacts are preserved under candidates/<candidate-digest>/.",
    ]
