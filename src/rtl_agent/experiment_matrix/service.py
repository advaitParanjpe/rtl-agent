from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from rtl_agent.artifacts import RunStore
from rtl_agent.config import AgentConfig, load_config
from rtl_agent.counterfactual import (
    InterventionError,
    PatchIntervention,
    ReplaceIntervention,
    apply_intervention,
    classify_outcome,
    intervention_digest,
)
from rtl_agent.counterfactual_models import FailureIdentity
from rtl_agent.execution.command_runner import CommandRunner
from rtl_agent.experiment_matrix.report import render_matrix_markdown, write_matrix_report
from rtl_agent.experiment_matrix_models import (
    ExperimentMatrixReport,
    InterventionEntry,
    InterventionManifest,
    MatrixRow,
    MatrixSummary,
)
from rtl_agent.failure_fingerprint import compare_fingerprint_reports, fingerprint_run
from rtl_agent.failure_fingerprint_models import FailureFingerprintReport
from rtl_agent.failure_intelligence_run import FailureIntelligenceRunError, run_failure_intelligence
from rtl_agent.failure_intelligence_run_models import FailureIntelligenceRunManifest
from rtl_agent.failure_report_models import FailureReport
from rtl_agent.git.worktree import GitWorktreeError, GitWorktreeManager
from rtl_agent.models import CommandResult, utc_now
from rtl_agent.reduction_models import STIMULUS_REDUCTION_SCHEMA_VERSION
from rtl_agent.run_inspection import RunInspectionError, inspect_run
from rtl_agent.stimulus import StimulusError, materialize_stimulus, parse_stimulus, stimulus_digest
from rtl_agent.stimulus_models import StructuredStimulus

_FAILING_VCD = "failing.vcd"
_PASSING_VCD = "passing.vcd"

_PARSER_NOTES = [
    "The experiment matrix composes the existing counterfactual intervention application, Git "
    "worktree isolation, command runner, triage, failure-intelligence orchestration, and "
    "fingerprint services; it adds no new analysis behaviour and no parallel analysis path.",
    "Each row records the observed fingerprint effect of one manual intervention against one "
    "minimized counterexample. It is not a root-cause claim and does not rank interventions by "
    "suspected cause.",
]


class ExperimentMatrixError(RuntimeError):
    pass


@dataclass
class _Baseline:
    run_dir: Path
    fingerprint: FailureFingerprintReport
    identity: FailureIdentity
    failure_time: int
    before: int
    after: int


def run_experiment_matrix(
    *,
    baseline_run: Path,
    reduction_report: Path,
    repo: Path,
    config_path: Path,
    command: str,
    interventions: Path,
    output: Path,
    max_experiments: int = 12,
    timeout: int | None = None,
    baseline_commit: str | None = None,
) -> ExperimentMatrixReport:
    """Run a bounded set of manual interventions against one minimized counterexample."""

    if max_experiments < 1:
        raise ExperimentMatrixError("max experiments must be at least 1")

    source_repo = repo.resolve()
    config = _load_config(config_path)
    if command not in config.commands:
        raise ExperimentMatrixError(f"unknown command: {command} (not in {config_path})")
    if timeout is not None:
        config = _with_timeout(config, command, timeout)

    baseline = _load_baseline(baseline_run)
    stimulus, stim_digest = _load_reduction_stimulus(reduction_report)
    manifest = _load_manifest(interventions)
    _validate_manifest(manifest)

    store = RunStore(output.resolve().parent, run_id=output.resolve().name)
    if store.run_dir.exists() and any(store.run_dir.iterdir()):
        raise ExperimentMatrixError(f"output directory is not empty: {store.run_dir}")
    store.create()
    experiment_dir = store.run_dir
    rows_root = experiment_dir / "rows"
    rows_root.mkdir(parents=True, exist_ok=True)

    manager = GitWorktreeManager(source_repo, experiment_dir)
    try:
        manager.validate_source_repo()
    except GitWorktreeError as exc:
        raise ExperimentMatrixError(str(exc)) from exc
    resolved_commit = _resolve_commit(source_repo, baseline_commit)

    warnings: list[str] = []
    cache: dict[str, MatrixRow] = {}
    rows: list[MatrixRow] = []
    executed = 0

    # Establish the comparison anchor by running the minimized counterexample with
    # no intervention. Interventions are measured against this reference, not the
    # original (full-stimulus) baseline whose absolute failure time differs.
    reference = _run_reference(
        manager,
        resolved_commit,
        config,
        command,
        baseline,
        stimulus,
        experiment_dir / "reference",
        warnings,
    )
    if reference.fingerprint.family_digest != baseline.fingerprint.family_digest:
        raise ExperimentMatrixError(
            "minimized counterexample does not reproduce the baseline failure family under "
            f"this command (baseline={baseline.fingerprint.family_digest[:12]}, "
            f"reference={reference.fingerprint.family_digest[:12]})"
        )

    for index, entry in enumerate(manifest.interventions):
        row_dir = rows_root / f"{index:02d}-{_slug(entry.id)}"
        intervention = _entry_intervention(entry, row_dir)
        digest = intervention_digest(intervention, entry.allowed_files)
        experiment_digest = _experiment_digest(
            resolved_commit, reference.fingerprint.family_digest, stim_digest, command, digest
        )
        base_row = _base_row(entry, digest, experiment_digest, reference)

        if not entry.enabled:
            rows.append(_finalize(base_row, "skipped", detail="intervention disabled"))
            continue
        if experiment_digest in cache:
            cached = cache[experiment_digest]
            rows.append(_from_cache(base_row, cached))
            continue
        if executed >= max_experiments:
            rows.append(_finalize(base_row, "skipped", detail="maximum experiment budget reached"))
            continue

        row_dir.mkdir(parents=True, exist_ok=True)
        row = _run_one(
            base_row,
            entry,
            intervention,
            manager,
            resolved_commit,
            config,
            command,
            reference,
            stimulus,
            row_dir,
            experiment_dir,
            warnings,
        )
        executed += 1
        cache[experiment_digest] = row
        rows.append(row)

    report = ExperimentMatrixReport(
        matrix_id=store.run_id,
        created_at=utc_now(),
        baseline_run=str(baseline.run_dir),
        baseline_exact_digest=baseline.fingerprint.exact_digest,
        baseline_family_digest=baseline.fingerprint.family_digest,
        baseline_failure_signals=list(baseline.identity.signals),
        baseline_failure_time=baseline.identity.failure_time,
        reference_exact_digest=reference.fingerprint.exact_digest,
        reference_family_digest=reference.fingerprint.family_digest,
        reference_failure_signals=list(reference.identity.signals),
        reference_failure_time=reference.identity.failure_time,
        reference_artifact_dir=(experiment_dir / "reference")
        .relative_to(experiment_dir)
        .as_posix(),
        target_repo=str(source_repo),
        target_commit=resolved_commit,
        command_name=command,
        minimized_stimulus=str(reduction_report.resolve().parent / "minimized-stimulus.json"),
        minimized_stimulus_digest=stim_digest,
        reduction_report=str(reduction_report),
        max_experiments=max_experiments,
        rows=rows,
        summary=_summary(rows),
        warnings=sorted(dict.fromkeys(warnings)),
        parser_notes=_PARSER_NOTES,
    )
    write_matrix_report(report, experiment_dir / "experiment-matrix.json")
    render_matrix_markdown(report, experiment_dir / "experiment-matrix.md")
    store.append_event("experiment_matrix", {"rows": len(rows), "executed": executed})
    return report


@dataclass
class _Outcome:
    fingerprint: FailureFingerprintReport | None
    identity: FailureIdentity
    command_status: str
    exit_code: int | None
    detail: str | None
    evidence_valid: bool


def _execute(
    stimulus: StructuredStimulus,
    worktree: Path,
    config: AgentConfig,
    command: str,
    before: int,
    after: int,
    fallback_time: int,
    run_dir: Path,
) -> _Outcome:
    """Materialize the minimized stimulus, run the command, and analyze the result."""

    materialize_stimulus(stimulus, worktree)
    _clear_waveforms(worktree)
    result = _run_command(config, command, worktree, run_dir)
    status = str(result.status)
    _preserve_command_logs(result, run_dir)
    empty = FailureIdentity()

    if status in {"timeout", "exec_error"}:
        return _Outcome(None, empty, status, result.exit_code, result.error, False)

    failing = worktree / _FAILING_VCD
    passing = worktree / _PASSING_VCD
    if not failing.exists() or not passing.exists():
        return _Outcome(
            None,
            empty,
            status,
            result.exit_code,
            "command did not produce failing/passing waveforms",
            False,
        )
    _preserve(failing, run_dir / _FAILING_VCD)
    _preserve(passing, run_dir / _PASSING_VCD)

    failure_time = _failure_time(run_dir, result, fallback_time)
    run_store = RunStore(run_dir, run_id="run")
    try:
        run_store.create()
        run_failure_intelligence(
            run_store,
            failing_vcd=failing,
            passing_vcd=passing,
            repository_root=_worktree_repo_root(worktree, config),
            failure_time=failure_time,
            before=before,
            after=after,
        )
    except FailureIntelligenceRunError as exc:
        return _Outcome(None, empty, status, result.exit_code, str(exc), False)

    fingerprint = fingerprint_run(run_store.run_dir)
    report_path = run_store.run_dir / "failure-report.json"
    try:
        failure_report = FailureReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        return _Outcome(None, empty, status, result.exit_code, str(exc), False)

    identity = FailureIdentity(
        failure_time=failure_report.earliest_divergence_time,
        signals=list(failure_report.earliest_divergence_signals),
        divergence_present=bool(failure_report.earliest_divergence_signals),
    )
    return _Outcome(fingerprint, identity, status, result.exit_code, None, True)


def _run_reference(
    manager: GitWorktreeManager,
    commit: str,
    config: AgentConfig,
    command: str,
    baseline: _Baseline,
    stimulus: StructuredStimulus,
    ref_dir: Path,
    warnings: list[str],
) -> _Baseline:
    ref_dir.mkdir(parents=True, exist_ok=True)
    try:
        plan = manager.create("reference", ref=commit)
    except GitWorktreeError as exc:
        raise ExperimentMatrixError(f"reference worktree creation failed: {exc}") from exc
    worktree = plan.worktree_path
    try:
        outcome = _execute(
            stimulus,
            worktree,
            config,
            command,
            baseline.before,
            baseline.after,
            baseline.failure_time,
            ref_dir,
        )
    finally:
        try:
            manager.remove(worktree)
        except GitWorktreeError as exc:
            warnings.append(f"reference worktree cleanup did not complete: {exc}")

    if outcome.fingerprint is None or outcome.fingerprint.insufficient_evidence:
        raise ExperimentMatrixError(
            "the minimized counterexample did not reproduce a usable failure fingerprint "
            f"under command '{command}': {outcome.detail or 'insufficient evidence'}"
        )
    return _Baseline(
        run_dir=ref_dir / "run",
        fingerprint=outcome.fingerprint,
        identity=outcome.identity,
        failure_time=outcome.identity.failure_time
        if outcome.identity.failure_time is not None
        else baseline.failure_time,
        before=baseline.before,
        after=baseline.after,
    )


def _run_one(
    base_row: MatrixRow,
    entry: InterventionEntry,
    intervention: PatchIntervention | ReplaceIntervention,
    manager: GitWorktreeManager,
    commit: str,
    config: AgentConfig,
    command: str,
    reference: _Baseline,
    stimulus: StructuredStimulus,
    row_dir: Path,
    experiment_dir: Path,
    warnings: list[str],
) -> MatrixRow:
    worktree_name = f"row-{row_dir.name}"
    try:
        plan = manager.create(worktree_name, ref=commit)
    except GitWorktreeError as exc:
        return _finalize(base_row, "invalid", detail=f"worktree creation failed: {exc}")
    worktree = plan.worktree_path
    try:
        try:
            files = apply_intervention(intervention, worktree, entry.allowed_files)
        except InterventionError as exc:
            return _finalize(base_row, "invalid", detail=str(exc))
        base_row.files_affected = files

        outcome = _execute(
            stimulus,
            worktree,
            config,
            command,
            reference.before,
            reference.after,
            reference.failure_time,
            row_dir,
        )
        base_row.command_status = outcome.command_status
        base_row.simulator_exit_code = outcome.exit_code
        base_row.artifact_dir = row_dir.relative_to(experiment_dir).as_posix()

        if outcome.fingerprint is None:
            return _classify_no_evidence(
                base_row, outcome.command_status, reference, outcome.detail
            )
        return _classify_evidence(base_row, outcome, reference)
    finally:
        try:
            manager.remove(worktree)
        except GitWorktreeError as exc:
            warnings.append(f"worktree cleanup did not complete: {exc}")


def _classify_evidence(base_row: MatrixRow, outcome: _Outcome, reference: _Baseline) -> MatrixRow:
    assert outcome.fingerprint is not None
    fingerprint = outcome.fingerprint
    identity = outcome.identity
    result_outcome, reasons = classify_outcome(
        command_status=outcome.command_status,
        intervention_evidence_valid=True,
        baseline=reference.identity,
        intervention=identity,
    )
    comparison = compare_fingerprint_reports(
        reference.fingerprint, fingerprint, left_path=Path("reference"), right_path=Path("result")
    )

    family_preserved = bool(identity.signals) and (
        fingerprint.family_digest == reference.fingerprint.family_digest
    )
    failure_removed = not identity.signals
    different_failure = bool(identity.signals) and (
        fingerprint.family_digest != reference.fingerprint.family_digest
    )
    time_shifted = (
        bool(identity.signals)
        and identity.failure_time is not None
        and reference.identity.failure_time is not None
        and identity.failure_time != reference.identity.failure_time
    )

    base_row.result_exact_digest = fingerprint.exact_digest
    base_row.result_family_digest = fingerprint.family_digest
    base_row.counterfactual_outcome = str(result_outcome)
    base_row.fingerprint_relation = str(comparison.match_kind)
    base_row.result_failure_signals = list(identity.signals)
    base_row.result_failure_time = identity.failure_time
    base_row.family_preserved = family_preserved
    base_row.failure_removed = failure_removed
    base_row.failure_time_shifted = time_shifted
    base_row.different_failure = different_failure
    base_row.insufficient_evidence_reasons = sorted(dict.fromkeys(reasons))
    return _finalize(base_row, "executed")


def _classify_no_evidence(
    base_row: MatrixRow, command_status: str, reference: _Baseline, detail: str | None
) -> MatrixRow:
    outcome, reasons = classify_outcome(
        command_status=command_status,
        intervention_evidence_valid=False,
        baseline=reference.identity,
        intervention=FailureIdentity(),
    )
    base_row.counterfactual_outcome = str(outcome)
    base_row.insufficient_evidence_reasons = sorted(
        dict.fromkeys([*reasons, *([detail] if detail else [])])
    )
    return _finalize(base_row, "executed", detail=detail)


def _base_row(
    entry: InterventionEntry, digest: str, experiment_digest: str, reference: _Baseline
) -> MatrixRow:
    # Each row is compared against the minimized-counterexample reference, so its
    # "baseline" digests/identity are the reference's (which shares the original
    # baseline's failure family, validated before any intervention runs).
    return MatrixRow(
        intervention_id=entry.id,
        description=entry.description,
        tags=list(entry.tags),
        enabled=entry.enabled,
        intervention_digest=digest,
        experiment_digest=experiment_digest,
        execution_status="pending",
        baseline_exact_digest=reference.fingerprint.exact_digest,
        baseline_family_digest=reference.fingerprint.family_digest,
        baseline_failure_signals=list(reference.identity.signals),
        baseline_failure_time=reference.identity.failure_time,
    )


def _finalize(row: MatrixRow, status: str, *, detail: str | None = None) -> MatrixRow:
    row.execution_status = status
    if detail is not None:
        row.detail = detail
    return row


def _from_cache(base_row: MatrixRow, cached: MatrixRow) -> MatrixRow:
    updated = cached.model_copy(
        update={
            "intervention_id": base_row.intervention_id,
            "description": base_row.description,
            "tags": base_row.tags,
            "from_cache": True,
        }
    )
    return updated


def _summary(rows: list[MatrixRow]) -> MatrixSummary:
    return MatrixSummary(
        total_requested=len(rows),
        executed=len([r for r in rows if r.execution_status == "executed" and not r.from_cache]),
        skipped=len([r for r in rows if r.execution_status in {"skipped", "invalid"}]),
        cache_hits=len([r for r in rows if r.from_cache]),
        failures_removed=len([r for r in rows if r.failure_removed]),
        same_family=len([r for r in rows if r.family_preserved and not r.failure_time_shifted]),
        changed_family=len([r for r in rows if r.different_failure]),
        no_effect=len([r for r in rows if r.counterfactual_outcome == "no_observable_effect"]),
        infrastructure_failures=len(
            [
                r
                for r in rows
                if r.execution_status in {"invalid"}
                or (r.command_status in {"timeout", "exec_error"})
            ]
        ),
        insufficient_evidence=len(
            [r for r in rows if r.counterfactual_outcome == "insufficient_evidence"]
        ),
    )


def _load_config(config_path: Path) -> AgentConfig:
    try:
        return load_config(config_path)
    except ValueError as exc:
        raise ExperimentMatrixError(str(exc)) from exc


def _with_timeout(config: AgentConfig, command: str, timeout: int) -> AgentConfig:
    spec = config.commands[command].model_copy(update={"timeout_seconds": timeout})
    commands = dict(config.commands)
    commands[command] = spec
    return config.model_copy(update={"commands": commands})


def _load_baseline(baseline_run: Path) -> _Baseline:
    resolved = baseline_run.resolve()
    try:
        inspection = inspect_run(resolved)
    except RunInspectionError as exc:
        raise ExperimentMatrixError(f"baseline run could not be inspected: {exc}") from exc
    if not inspection.valid:
        raise ExperimentMatrixError(
            f"refusing to use an invalid baseline run: {resolved} "
            f"(status={inspection.manifest_status})"
        )
    manifest_path = resolved / "run-manifest.json"
    try:
        manifest = FailureIntelligenceRunManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError, ValueError) as exc:
        raise ExperimentMatrixError(
            f"baseline run manifest is unreadable: {manifest_path}"
        ) from exc
    report_path = resolved / (manifest.failure_report_path or "failure-report.json")
    try:
        failure_report = FailureReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise ExperimentMatrixError(
            f"baseline failure report is unreadable: {report_path}"
        ) from exc
    fingerprint = fingerprint_run(resolved)
    if fingerprint.insufficient_evidence:
        raise ExperimentMatrixError(
            "baseline fingerprint has insufficient evidence to anchor a failure family"
        )
    identity = FailureIdentity(
        failure_time=failure_report.earliest_divergence_time,
        signals=list(failure_report.earliest_divergence_signals),
        divergence_present=bool(failure_report.earliest_divergence_signals),
    )
    return _Baseline(
        run_dir=resolved,
        fingerprint=fingerprint,
        identity=identity,
        failure_time=manifest.failure_time,
        before=manifest.before,
        after=manifest.after,
    )


def _load_reduction_stimulus(reduction_report: Path) -> tuple[StructuredStimulus, str]:
    resolved = reduction_report.resolve()
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ExperimentMatrixError(f"reduction report is unreadable: {resolved}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != STIMULUS_REDUCTION_SCHEMA_VERSION:
        raise ExperimentMatrixError(f"unsupported or malformed reduction report: {resolved}")
    recorded_digest = raw.get("minimized_stimulus_digest")
    stimulus_path = resolved.parent / "minimized-stimulus.json"
    try:
        stimulus = parse_stimulus(stimulus_path)
    except StimulusError as exc:
        raise ExperimentMatrixError(f"minimized stimulus is unreadable: {exc}") from exc
    digest = stimulus_digest(stimulus)
    if recorded_digest != digest:
        raise ExperimentMatrixError(
            "minimized stimulus does not match the reduction report digest "
            f"(report={recorded_digest}, stimulus={digest})"
        )
    return stimulus, digest


def _load_manifest(interventions: Path) -> InterventionManifest:
    try:
        raw = interventions.read_text(encoding="utf-8")
    except OSError as exc:
        raise ExperimentMatrixError(f"interventions manifest not found: {interventions}") from exc
    try:
        return InterventionManifest.model_validate_json(raw)
    except (ValidationError, ValueError) as exc:
        raise ExperimentMatrixError(f"malformed interventions manifest: {exc}") from exc


def _validate_manifest(manifest: InterventionManifest) -> None:
    if not manifest.interventions:
        raise ExperimentMatrixError("interventions manifest is empty")
    seen: set[str] = set()
    for entry in manifest.interventions:
        if not entry.id:
            raise ExperimentMatrixError("intervention entry has an empty id")
        if entry.id in seen:
            raise ExperimentMatrixError(f"duplicate intervention id: {entry.id}")
        seen.add(entry.id)
        if not entry.allowed_files:
            raise ExperimentMatrixError(f"intervention has no allowed files: {entry.id}")
        if (entry.patch is None) == (entry.replace is None):
            raise ExperimentMatrixError(
                f"intervention must have exactly one of patch or replace: {entry.id}"
            )


def _entry_intervention(
    entry: InterventionEntry, row_dir: Path
) -> PatchIntervention | ReplaceIntervention:
    if entry.replace is not None:
        return ReplaceIntervention(
            file=entry.replace.file,
            old=entry.replace.old,
            new=entry.replace.new,
            description=entry.description,
        )
    assert entry.patch is not None
    row_dir.mkdir(parents=True, exist_ok=True)
    patch_path = row_dir / "intervention.patch"
    patch_path.write_text(entry.patch, encoding="utf-8")
    return PatchIntervention(patch_path=patch_path, description=entry.description)


def _run_command(config: AgentConfig, command: str, worktree: Path, row_dir: Path) -> CommandResult:
    worktree_config = config.model_copy(
        update={
            "run_artifact_dir": row_dir.resolve(),
            "allowed_working_paths": [Path(".")],
            "protected_paths": [],
            "config_path": worktree / "rtl-agent.yaml",
        }
    )
    store = RunStore(row_dir, run_id="_command")
    store.run_dir = row_dir
    store.commands_dir = row_dir / "commands"
    runner = CommandRunner(worktree_config, store)
    return runner.run_named(command)


def _worktree_repo_root(worktree: Path, config: AgentConfig) -> Path:
    repository_path = config.repository_path
    if repository_path.is_absolute():
        return worktree
    return (worktree / repository_path).resolve()


def _failure_time(row_dir: Path, result: CommandResult, fallback: int) -> int:
    import re

    from rtl_agent.triage import triage_command_result

    result_path = row_dir / "commands" / result.command_id / "result.json"
    if not result_path.exists():
        return fallback
    try:
        triage = triage_command_result(result_path)
    except Exception:  # noqa: BLE001 - best-effort; fall back to the baseline time.
        return fallback
    for assertion in triage.assertion_failures:
        if assertion.time_context:
            match = re.search(r"[0-9][0-9_]*", assertion.time_context)
            if match:
                return int(match.group(0).replace("_", ""))
    return fallback


def _clear_waveforms(worktree: Path) -> None:
    for name in (_FAILING_VCD, _PASSING_VCD):
        path = worktree / name
        if path.exists():
            path.unlink()


def _preserve(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _preserve_command_logs(result: CommandResult, row_dir: Path) -> None:
    for path in (result.stdout_path, result.stderr_path):
        if path.exists() and not path.is_relative_to(row_dir):
            _preserve(path, row_dir / path.name)


def _resolve_commit(source_repo: Path, baseline_commit: str | None) -> str:
    ref = baseline_commit or "HEAD"
    result = subprocess.run(
        ["git", "-C", str(source_repo), "rev-parse", ref],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ExperimentMatrixError(
            f"could not resolve commit '{ref}' in {source_repo}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _experiment_digest(
    commit: str, baseline_family: str, stim_digest: str, command: str, intervention: str
) -> str:
    from hashlib import sha256

    payload = json.dumps(
        {
            "commit": commit,
            "baseline_family": baseline_family,
            "stimulus": stim_digest,
            "command": command,
            "intervention": intervention,
        },
        sort_keys=True,
    )
    return sha256((payload + "\n").encode("utf-8")).hexdigest()


def _slug(value: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in value)[:40] or "row"
