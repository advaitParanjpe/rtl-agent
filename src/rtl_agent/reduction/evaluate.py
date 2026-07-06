from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from rtl_agent.artifacts import RunStore
from rtl_agent.config import AgentConfig
from rtl_agent.execution.command_runner import CommandRunner
from rtl_agent.failure_fingerprint import fingerprint_run
from rtl_agent.failure_fingerprint_models import FailureFingerprintReport
from rtl_agent.failure_intelligence_run import FailureIntelligenceRunError, run_failure_intelligence
from rtl_agent.models import CommandResult
from rtl_agent.reduction_models import (
    PRESERVING_CLASSES,
    CandidateEvaluation,
    PreservationClass,
    SimulatorResultSummary,
)
from rtl_agent.stimulus import materialize_stimulus, stimulus_digest, subset_by_ids
from rtl_agent.stimulus_models import StructuredStimulus
from rtl_agent.triage import triage_command_result

FAILING_VCD_NAME = "failing.vcd"
PASSING_VCD_NAME = "passing.vcd"

_TIME_RE = re.compile(r"([0-9][0-9_]*)")


@dataclass
class BaselineFingerprint:
    exact_digest: str
    family_digest: str
    failure_time: int
    before: int
    after: int


@dataclass
class EvaluationContext:
    worktree_path: Path
    config: AgentConfig
    command: str
    repository_root: Path
    candidates_root: Path
    baseline: BaselineFingerprint


def evaluate_candidate(
    context: EvaluationContext, original: StructuredStimulus, retained_ids: list[str]
) -> tuple[CandidateEvaluation, SimulatorResultSummary]:
    """Materialize and evaluate one candidate reduced stimulus in the worktree."""

    candidate = subset_by_ids(original, retained_ids)
    digest = stimulus_digest(candidate)
    candidate_dir = context.candidates_root / digest
    candidate_dir.mkdir(parents=True, exist_ok=True)

    materialize_stimulus(candidate, context.worktree_path)
    _clear_stale_waveforms(context.worktree_path)
    shutil.copyfile(
        context.worktree_path / "sim" / "stimulus.json", candidate_dir / "stimulus.json"
    )

    result = _run_command(context, candidate_dir)
    summary = SimulatorResultSummary(
        command_name=context.command,
        status=str(result.status),
        exit_code=result.exit_code,
        timeout_seconds=_timeout_for(context.config, context.command),
    )

    def record(
        classification: PreservationClass,
        detail: str | None = None,
        fingerprint: FailureFingerprintReport | None = None,
    ) -> tuple[CandidateEvaluation, SimulatorResultSummary]:
        evaluation = _evaluation(
            digest,
            candidate,
            classification,
            result,
            candidate_dir,
            context.candidates_root,
            fingerprint,
            detail,
        )
        return evaluation, summary

    if str(result.status) == "timeout":
        return record(PreservationClass.TIMED_OUT, detail=result.error)
    if str(result.status) == "exec_error":
        return record(PreservationClass.EXECUTION_FAILED, detail=result.error)

    failing = context.worktree_path / FAILING_VCD_NAME
    passing = context.worktree_path / PASSING_VCD_NAME
    if not failing.exists() or not passing.exists():
        return record(
            PreservationClass.EXECUTION_FAILED,
            detail="command did not produce the expected failing/passing waveforms",
        )

    failure_time = _failure_time(candidate_dir, result, context.baseline.failure_time)
    run_dir = candidate_dir / "run"
    run_store = RunStore(candidate_dir, run_id="run")
    try:
        run_store.create()
        run_failure_intelligence(
            run_store,
            failing_vcd=failing,
            passing_vcd=passing,
            repository_root=context.repository_root,
            failure_time=failure_time,
            before=context.baseline.before,
            after=context.baseline.after,
        )
    except FailureIntelligenceRunError as exc:
        return record(PreservationClass.EXECUTION_FAILED, detail=str(exc))

    fingerprint = fingerprint_run(run_dir)
    classification = _classify(fingerprint, context.baseline)
    return record(classification, fingerprint=fingerprint)


def _classify(
    fingerprint: FailureFingerprintReport, baseline: BaselineFingerprint
) -> PreservationClass:
    # No observed divergence means the failure is gone, even though the
    # fingerprint marks that as insufficient evidence of a failure.
    if not fingerprint.earliest_divergent_signals:
        return PreservationClass.FAILURE_REMOVED
    if fingerprint.insufficient_evidence:
        return PreservationClass.INSUFFICIENT_EVIDENCE
    if fingerprint.exact_digest == baseline.exact_digest:
        return PreservationClass.SAME_FAILURE_EXACT
    if fingerprint.family_digest == baseline.family_digest:
        return PreservationClass.SAME_FAILURE_FAMILY
    return PreservationClass.DIFFERENT_FAILURE


def _evaluation(
    digest: str,
    candidate: StructuredStimulus,
    classification: PreservationClass,
    result: CommandResult,
    candidate_dir: Path,
    candidates_root: Path,
    fingerprint: FailureFingerprintReport | None,
    detail: str | None,
) -> CandidateEvaluation:
    return CandidateEvaluation(
        candidate_digest=digest,
        item_count=len(candidate.items),
        retained_item_ids=[item.id for item in candidate.items],
        classification=classification,
        preserves=classification in PRESERVING_CLASSES,
        command_status=str(result.status),
        command_exit_code=result.exit_code,
        fingerprint_exact_digest=fingerprint.exact_digest if fingerprint else None,
        fingerprint_family_digest=fingerprint.family_digest if fingerprint else None,
        artifact_dir=candidate_dir.relative_to(candidates_root.parent).as_posix(),
        detail=detail,
    )


def _run_command(context: EvaluationContext, candidate_dir: Path) -> CommandResult:
    worktree_config = context.config.model_copy(
        update={
            "run_artifact_dir": candidate_dir.resolve(),
            "allowed_working_paths": [Path(".")],
            "protected_paths": [],
            "config_path": context.worktree_path / "rtl-agent.yaml",
        }
    )
    store = RunStore(candidate_dir, run_id="_command")
    store.run_dir = candidate_dir
    store.commands_dir = candidate_dir / "commands"
    runner = CommandRunner(worktree_config, store)
    return runner.run_named(context.command)


def _clear_stale_waveforms(worktree: Path) -> None:
    for name in (FAILING_VCD_NAME, PASSING_VCD_NAME):
        path = worktree / name
        if path.exists():
            path.unlink()


def _failure_time(candidate_dir: Path, result: CommandResult, fallback: int) -> int:
    result_path = candidate_dir / "commands" / result.command_id / "result.json"
    if not result_path.exists():
        return fallback
    try:
        triage = triage_command_result(result_path)
    except Exception:  # noqa: BLE001 - triage is best-effort here; fall back to baseline time.
        return fallback
    for assertion in triage.assertion_failures:
        if assertion.time_context:
            match = _TIME_RE.search(assertion.time_context)
            if match:
                return int(match.group(1).replace("_", ""))
    return fallback


def _timeout_for(config: AgentConfig, command: str) -> int:
    spec = config.commands[command]
    return spec.timeout_seconds or config.execution.timeout_seconds
