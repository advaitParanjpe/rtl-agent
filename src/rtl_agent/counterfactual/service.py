from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from rtl_agent.artifacts import RunStore
from rtl_agent.config import AgentConfig, load_config
from rtl_agent.counterfactual.classify import classify_outcome
from rtl_agent.counterfactual.report import render_experiment_markdown, write_experiment_report
from rtl_agent.counterfactual_models import (
    BaselineReference,
    CounterfactualExperimentReport,
    ExecutionRecord,
    FailureIdentity,
    GeneratedArtifact,
    InterventionKind,
    InterventionSpec,
    ObservableDifference,
    WorktreeProvenance,
)
from rtl_agent.execution.command_runner import CommandRunner
from rtl_agent.failure_intelligence_run import (
    FailureIntelligenceRunError,
    run_failure_intelligence,
    sha256_file,
)
from rtl_agent.failure_intelligence_run_models import FailureIntelligenceRunManifest
from rtl_agent.failure_report_models import FailureReport
from rtl_agent.git.worktree import GitWorktreeError, GitWorktreeManager
from rtl_agent.models import CommandResult, utc_now
from rtl_agent.run_inspection import RunInspectionError, inspect_run
from rtl_agent.triage import triage_command_result

_PARSER_NOTES = [
    "The counterfactual runner reuses the existing command runner, Git worktree, triage, "
    "assertion-linking, waveform, comparison, failure-intelligence, and inspection services; "
    "it adds no new analysis behaviour and no parallel analysis path.",
    "Outcome classification is deterministic and evidence-based (divergent-signal sets, "
    "failure timestamps, command status, artifact validity). It never asserts causality.",
]


class CounterfactualError(RuntimeError):
    pass


@dataclass
class _PatchIntervention:
    patch_path: Path
    description: str | None


@dataclass
class _ReplaceIntervention:
    file: str
    old: str
    new: str
    description: str | None


def run_counterfactual(
    *,
    baseline_run: Path,
    repo: Path,
    config_path: Path,
    command: str,
    output_run: Path,
    allowed_files: list[str],
    patch: Path | None = None,
    replace_file: str | None = None,
    replace_old: str | None = None,
    replace_new: str | None = None,
    baseline_commit: str | None = None,
    description: str | None = None,
) -> CounterfactualExperimentReport:
    """Run one manual counterfactual intervention experiment (see current milestone)."""

    if not allowed_files:
        raise CounterfactualError("at least one --allowed-file is required")
    intervention = _normalize_intervention(
        patch, replace_file, replace_old, replace_new, description
    )
    source_repo = repo.resolve()

    config = _load_config(config_path)
    if command not in config.commands:
        raise CounterfactualError(f"unknown command: {command} (not in {config_path})")

    baseline_ref, baseline_identity, manifest = _load_baseline(baseline_run)

    store = RunStore(output_run.resolve().parent, run_id=output_run.resolve().name)
    if store.run_dir.exists() and any(store.run_dir.iterdir()):
        raise CounterfactualError(f"output run directory is not empty: {store.run_dir}")
    store.create()
    experiment_dir = store.run_dir

    intervention_spec = _preserve_intervention(intervention, experiment_dir, allowed_files)

    manager = GitWorktreeManager(source_repo, experiment_dir)
    try:
        manager.validate_source_repo()
    except GitWorktreeError as exc:
        raise CounterfactualError(str(exc)) from exc
    resolved_commit = _resolve_commit(source_repo, baseline_commit)
    repo_dirty = _is_dirty(source_repo)

    warnings: list[str] = []
    if repo_dirty:
        warnings.append(
            "target repository has uncommitted changes; the experiment runs on an isolated "
            "worktree of the recorded commit and does not include them"
        )

    plan = manager.create("intervention", ref=resolved_commit)
    worktree_path = plan.worktree_path
    worktree = WorktreeProvenance(
        source_repo=str(source_repo),
        baseline_commit=resolved_commit,
        worktree_path=str(worktree_path),
    )

    execution: ExecutionRecord | None = None
    intervention_identity = FailureIdentity()
    generated: list[GeneratedArtifact] = []
    insufficient_reasons: list[str] = []
    command_status = "not_run"
    intervention_evidence_valid = False

    try:
        target_files = _apply_intervention(intervention, worktree_path, allowed_files)
        intervention_spec.applied = True
        intervention_spec.target_files = target_files
        intervention_spec.apply_detail = "intervention applied cleanly in isolated worktree"

        result = _run_command(config, command, worktree_path, experiment_dir)
        command_status = str(result.status)
        triage = triage_command_result(_command_result_path(experiment_dir, result))
        waveform_refs = [ref.path for ref in triage.waveform_references]
        assertion_label = None
        assertion_time = None
        if triage.assertion_failures:
            assertion_label = triage.assertion_failures[0].signal_or_label
            assertion_time = triage.assertion_failures[0].time_context

        execution = ExecutionRecord(
            command_name=command,
            argv=list(result.argv),
            cwd=str(result.cwd),
            status=command_status,
            exit_code=result.exit_code,
            duration_seconds=round(result.duration_seconds, 6),
            timeout_seconds=_timeout_for(config, command),
            stdout_relative_path=_relative(result.stdout_path, experiment_dir),
            stderr_relative_path=_relative(result.stderr_path, experiment_dir),
            error=result.error,
            waveform_references=sorted(dict.fromkeys(waveform_refs)),
        )
        _record_command_logs(result, experiment_dir, generated)

        if command_status in {"timeout", "exec_error"}:
            insufficient_reasons.append(execution.error or "command did not run to completion")
        else:
            intervention_vcd = _select_waveform(triage.waveform_references, experiment_dir)
            if intervention_vcd is None:
                insufficient_reasons.append(
                    "no generated VCD waveform was captured from the intervention run"
                )
            else:
                generated.append(
                    _artifact("intervention_waveform", intervention_vcd, experiment_dir)
                )
                intervention_identity, intervention_evidence_valid = _analyze_intervention(
                    experiment_dir,
                    worktree_path,
                    config,
                    intervention_vcd,
                    manifest,
                    baseline_ref,
                    assertion_label,
                    assertion_time,
                    generated,
                    insufficient_reasons,
                )
    finally:
        _remove_worktree(manager, worktree_path, worktree, warnings)

    outcome, classify_reasons = classify_outcome(
        command_status=command_status,
        intervention_evidence_valid=intervention_evidence_valid,
        baseline=baseline_identity,
        intervention=intervention_identity,
    )
    insufficient_reasons.extend(
        reason for reason in classify_reasons if reason not in insufficient_reasons
    )

    report = CounterfactualExperimentReport(
        experiment_id=store.run_id,
        created_at=utc_now(),
        target_repo=str(source_repo),
        baseline_commit=resolved_commit,
        baseline=baseline_ref,
        intervention=intervention_spec,
        worktree=worktree,
        execution=execution,
        baseline_failure=baseline_identity,
        intervention_failure=intervention_identity,
        outcome=outcome,
        observable_differences=_observable_differences(baseline_identity, intervention_identity),
        generated_artifacts=sorted(generated, key=lambda item: item.relative_path),
        warnings=sorted(dict.fromkeys(warnings)),
        insufficient_evidence_reasons=sorted(dict.fromkeys(insufficient_reasons)),
        parser_notes=_PARSER_NOTES,
    )
    write_experiment_report(report, experiment_dir / "experiment-report.json")
    render_experiment_markdown(report, experiment_dir / "experiment-report.md")
    store.append_event("counterfactual_experiment", {"outcome": str(outcome)})
    return report


def _normalize_intervention(
    patch: Path | None,
    replace_file: str | None,
    replace_old: str | None,
    replace_new: str | None,
    description: str | None,
) -> _PatchIntervention | _ReplaceIntervention:
    has_patch = patch is not None
    has_replace = replace_file is not None or replace_old is not None or replace_new is not None
    if has_patch and has_replace:
        raise CounterfactualError("provide either a --patch or a replace_text edit, not both")
    if has_patch:
        assert patch is not None
        if not patch.exists() or not patch.is_file():
            raise CounterfactualError(f"patch file not found: {patch}")
        return _PatchIntervention(patch_path=patch.resolve(), description=description)
    if replace_file is None or replace_old is None or replace_new is None:
        raise CounterfactualError(
            "a replace_text edit requires --replace-file, --replace-old, and --replace-new"
        )
    return _ReplaceIntervention(
        file=replace_file, old=replace_old, new=replace_new, description=description
    )


def _load_config(config_path: Path) -> AgentConfig:
    try:
        return load_config(config_path)
    except ValueError as exc:
        raise CounterfactualError(str(exc)) from exc


def _load_baseline(
    baseline_run: Path,
) -> tuple[BaselineReference, FailureIdentity, FailureIntelligenceRunManifest]:
    resolved = baseline_run.resolve()
    try:
        inspection = inspect_run(resolved)
    except RunInspectionError as exc:
        raise CounterfactualError(f"baseline run could not be inspected: {exc}") from exc
    if not inspection.valid:
        raise CounterfactualError(
            f"refusing to use an invalid baseline run: {resolved} "
            f"(status={inspection.manifest_status}, invalid={inspection.invalid_artifacts}, "
            f"missing={inspection.missing_artifacts})"
        )

    manifest_path = resolved / "run-manifest.json"
    try:
        manifest = FailureIntelligenceRunManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError, ValueError) as exc:
        raise CounterfactualError(f"baseline run manifest is unreadable: {manifest_path}") from exc

    report_rel = manifest.failure_report_path or "failure-report.json"
    report_path = resolved / report_rel
    try:
        report = FailureReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise CounterfactualError(f"baseline failure report is unreadable: {report_path}") from exc

    passing = manifest.passing_vcd
    baseline_ref = BaselineReference(
        run_dir=str(resolved),
        run_id=manifest.run_id,
        manifest_sha256=sha256_file(manifest_path),
        failure_report_sha256=sha256_file(report_path) if report_path.exists() else None,
        valid=True,
        status=str(manifest.status),
        passing_reference=str(passing),
        passing_reference_exists=passing.exists(),
    )
    identity = FailureIdentity(
        failure_time=report.earliest_divergence_time,
        signals=list(report.earliest_divergence_signals),
        divergence_present=bool(report.earliest_divergence_signals),
    )
    return baseline_ref, identity, manifest


def _preserve_intervention(
    intervention: _PatchIntervention | _ReplaceIntervention,
    experiment_dir: Path,
    allowed_files: list[str],
) -> InterventionSpec:
    intervention_dir = experiment_dir / "intervention"
    intervention_dir.mkdir(parents=True, exist_ok=True)
    if isinstance(intervention, _PatchIntervention):
        artifact = intervention_dir / "intervention.patch"
        shutil.copyfile(intervention.patch_path, artifact)
        return InterventionSpec(
            kind=InterventionKind.PATCH,
            description=intervention.description,
            allowed_files=list(allowed_files),
            artifact_relative_path=_relative(artifact, experiment_dir) or "intervention.patch",
        )
    artifact = intervention_dir / "intervention.json"
    edit: dict[str, object] = {
        "file": intervention.file,
        "old": intervention.old,
        "new": intervention.new,
    }
    artifact.write_text(_json_dumps(edit), encoding="utf-8")
    return InterventionSpec(
        kind=InterventionKind.REPLACE_TEXT,
        description=intervention.description,
        allowed_files=list(allowed_files),
        artifact_relative_path=_relative(artifact, experiment_dir) or "intervention.json",
        replace_file=intervention.file,
        replace_old=intervention.old,
        replace_new=intervention.new,
    )


def _apply_intervention(
    intervention: _PatchIntervention | _ReplaceIntervention,
    worktree_path: Path,
    allowed_files: list[str],
) -> list[str]:
    if isinstance(intervention, _PatchIntervention):
        return _apply_patch(intervention.patch_path, worktree_path, allowed_files)
    return _apply_replace(intervention, worktree_path, allowed_files)


def _apply_patch(patch_path: Path, worktree_path: Path, allowed_files: list[str]) -> list[str]:
    targets = _patch_target_files(patch_path, worktree_path)
    if not targets:
        raise CounterfactualError("patch does not modify any files")
    disallowed = [name for name in targets if name not in allowed_files]
    if disallowed:
        raise CounterfactualError(
            f"intervention targets files not in --allowed-file: {', '.join(sorted(disallowed))}"
        )
    check = subprocess.run(
        ["git", "-C", str(worktree_path), "apply", "--check", str(patch_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if check.returncode != 0:
        raise CounterfactualError(
            f"patch does not apply cleanly: {check.stderr.strip() or 'git apply --check failed'}"
        )
    applied = subprocess.run(
        ["git", "-C", str(worktree_path), "apply", str(patch_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if applied.returncode != 0:
        raise CounterfactualError(
            f"patch failed to apply: {applied.stderr.strip() or 'git apply failed'}"
        )
    return sorted(targets)


def _patch_target_files(patch_path: Path, worktree_path: Path) -> list[str]:
    numstat = subprocess.run(
        ["git", "-C", str(worktree_path), "apply", "--numstat", str(patch_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if numstat.returncode != 0:
        raise CounterfactualError(
            f"patch could not be parsed: {numstat.stderr.strip() or 'git apply --numstat failed'}"
        )
    files: list[str] = []
    for line in numstat.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[2]:
            files.append(parts[2])
    return files


def _apply_replace(
    intervention: _ReplaceIntervention, worktree_path: Path, allowed_files: list[str]
) -> list[str]:
    if intervention.file not in allowed_files:
        raise CounterfactualError(
            f"intervention targets a file not in --allowed-file: {intervention.file}"
        )
    target = (worktree_path / intervention.file).resolve()
    if not target.is_relative_to(worktree_path.resolve()):
        raise CounterfactualError(f"intervention file escapes the worktree: {intervention.file}")
    if not target.exists() or not target.is_file():
        raise CounterfactualError(f"intervention file does not exist: {intervention.file}")
    text = target.read_text(encoding="utf-8")
    occurrences = text.count(intervention.old)
    if occurrences != 1:
        raise CounterfactualError(
            f"replace_text expected exactly one match in {intervention.file}, found {occurrences}"
        )
    target.write_text(text.replace(intervention.old, intervention.new, 1), encoding="utf-8")
    return [intervention.file]


def _run_command(
    config: AgentConfig, command: str, worktree_path: Path, experiment_dir: Path
) -> CommandResult:
    worktree_config = config.model_copy(
        update={
            "repository_path": Path("."),
            "run_artifact_dir": experiment_dir.resolve(),
            "allowed_working_paths": [Path(".")],
            "protected_paths": [],
            "config_path": worktree_path / "rtl-agent.yaml",
        }
    )
    store = RunStore(experiment_dir, run_id="_command_run")
    store.run_dir = experiment_dir
    store.commands_dir = experiment_dir / "commands"
    runner = CommandRunner(worktree_config, store)
    try:
        return runner.run_named(command)
    except (KeyError, ValueError) as exc:
        raise CounterfactualError(f"command execution setup failed: {exc}") from exc


def _analyze_intervention(
    experiment_dir: Path,
    worktree_path: Path,
    config: AgentConfig,
    intervention_vcd: Path,
    manifest: FailureIntelligenceRunManifest,
    baseline_ref: BaselineReference,
    assertion_label: str | None,
    assertion_time: str | None,
    generated: list[GeneratedArtifact],
    insufficient_reasons: list[str],
) -> tuple[FailureIdentity, bool]:
    passing = Path(baseline_ref.passing_reference) if baseline_ref.passing_reference else None
    if passing is None or not passing.exists():
        insufficient_reasons.append(
            "baseline passing reference waveform is unavailable for comparison"
        )
        return FailureIdentity(
            assertion_label=assertion_label, assertion_time=assertion_time
        ), False

    repo_root = _worktree_repo_root(worktree_path, config, manifest)
    run_store = RunStore(experiment_dir, run_id="intervention-run")
    try:
        run_store.create()
        run_failure_intelligence(
            run_store,
            failing_vcd=intervention_vcd,
            passing_vcd=passing,
            repository_root=repo_root,
            failure_time=manifest.failure_time,
            before=manifest.before,
            after=manifest.after,
        )
    except FailureIntelligenceRunError as exc:
        insufficient_reasons.append(f"intervention failure-intelligence run failed: {exc}")
        return FailureIdentity(
            assertion_label=assertion_label, assertion_time=assertion_time
        ), False

    report_path = run_store.run_dir / "failure-report.json"
    if not report_path.exists():
        insufficient_reasons.append("intervention run did not produce a failure report")
        return FailureIdentity(
            assertion_label=assertion_label, assertion_time=assertion_time
        ), False
    try:
        report = FailureReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError):
        insufficient_reasons.append("intervention failure report is unreadable")
        return FailureIdentity(
            assertion_label=assertion_label, assertion_time=assertion_time
        ), False

    generated.append(_artifact("intervention_failure_report", report_path, experiment_dir))
    identity = FailureIdentity(
        failure_time=report.earliest_divergence_time,
        signals=list(report.earliest_divergence_signals),
        assertion_label=assertion_label,
        assertion_time=assertion_time,
        divergence_present=bool(report.earliest_divergence_signals),
    )
    return identity, True


def _worktree_repo_root(
    worktree_path: Path, config: AgentConfig, manifest: FailureIntelligenceRunManifest
) -> Path:
    repository_path = config.repository_path
    if repository_path.is_absolute():
        return worktree_path
    return (worktree_path / repository_path).resolve()


def _select_waveform(references: object, experiment_dir: Path) -> Path | None:
    from rtl_agent.triage_models import WaveformReference

    assert isinstance(references, list)
    waveform_dir = experiment_dir / "waveform"
    for reference in references:
        assert isinstance(reference, WaveformReference)
        if not reference.path.endswith(".vcd") or not reference.exists:
            continue
        resolved = reference.resolved_path
        if resolved is None or not resolved.exists():
            continue
        waveform_dir.mkdir(parents=True, exist_ok=True)
        destination = waveform_dir / "intervention.vcd"
        shutil.copyfile(resolved, destination)
        return destination
    return None


def _record_command_logs(
    result: CommandResult, experiment_dir: Path, generated: list[GeneratedArtifact]
) -> None:
    for role, path in (
        ("command_stdout", result.stdout_path),
        ("command_stderr", result.stderr_path),
    ):
        if path.exists():
            generated.append(_artifact(role, path, experiment_dir))


def _command_result_path(experiment_dir: Path, result: CommandResult) -> Path:
    return experiment_dir / "commands" / result.command_id / "result.json"


def _resolve_commit(source_repo: Path, baseline_commit: str | None) -> str:
    ref = baseline_commit or "HEAD"
    result = subprocess.run(
        ["git", "-C", str(source_repo), "rev-parse", ref],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise CounterfactualError(
            f"could not resolve baseline commit '{ref}' in {source_repo}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _is_dirty(source_repo: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(source_repo), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _remove_worktree(
    manager: GitWorktreeManager,
    worktree_path: Path,
    worktree: WorktreeProvenance,
    warnings: list[str],
) -> None:
    try:
        manager.remove(worktree_path)
        worktree.removed = True
    except GitWorktreeError as exc:
        warnings.append(f"worktree cleanup did not complete: {exc}")
        worktree.removed = not worktree_path.exists()


def _observable_differences(
    baseline: FailureIdentity, intervention: FailureIdentity
) -> list[ObservableDifference]:
    differences: list[ObservableDifference] = []
    if baseline.failure_time != intervention.failure_time:
        differences.append(
            ObservableDifference(
                field="failure_time",
                baseline=_str_or_none(baseline.failure_time),
                intervention=_str_or_none(intervention.failure_time),
            )
        )
    if set(baseline.signals) != set(intervention.signals):
        differences.append(
            ObservableDifference(
                field="divergent_signals",
                baseline=", ".join(sorted(baseline.signals)) or None,
                intervention=", ".join(sorted(intervention.signals)) or None,
            )
        )
    if baseline.divergence_present != intervention.divergence_present:
        differences.append(
            ObservableDifference(
                field="divergence_present",
                baseline=str(baseline.divergence_present),
                intervention=str(intervention.divergence_present),
            )
        )
    return differences


def _artifact(role: str, path: Path, experiment_dir: Path) -> GeneratedArtifact:
    return GeneratedArtifact(
        role=role,
        relative_path=_relative(path, experiment_dir) or path.name,
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
    )


def _relative(path: Path, base: Path) -> str | None:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return None


def _timeout_for(config: AgentConfig, command: str) -> int:
    spec = config.commands[command]
    return spec.timeout_seconds or config.execution.timeout_seconds


def _str_or_none(value: object) -> str | None:
    return None if value is None else str(value)


def _json_dumps(data: dict[str, object]) -> str:
    import json

    return json.dumps(data, indent=2, sort_keys=True) + "\n"
