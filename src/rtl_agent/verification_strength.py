from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import ValidationError

from rtl_agent.implementation_models import (
    ImplementationReport,
    ValidationResultSummary,
    VerificationFailureCategory,
)
from rtl_agent.models import CommandResult
from rtl_agent.repository_map import RepositoryMap
from rtl_agent.review_models import EvidenceCitation, ReviewFindingSeverity, ReviewReport
from rtl_agent.task_contract import TaskContract
from rtl_agent.triage_models import TriageReport
from rtl_agent.verification_strength_models import (
    VerificationSignalKind,
    VerificationStrengthLevel,
    VerificationStrengthReport,
    VerificationStrengthSignal,
    WeakPatternSeverity,
    WeakValidationPattern,
)


class VerificationStrengthError(RuntimeError):
    pass


def assess_verification_strength(
    task_contract_path: Path,
    repository_map_path: Path,
    implementation_report_path: Path,
    review_report_path: Path | None = None,
    triage_report_paths: list[Path] | None = None,
) -> VerificationStrengthReport:
    triage_report_paths = triage_report_paths or []
    try:
        task_contract = TaskContract.model_validate_json(
            task_contract_path.read_text(encoding="utf-8")
        )
        repository_map = RepositoryMap.model_validate_json(
            repository_map_path.read_text(encoding="utf-8")
        )
        implementation_report = ImplementationReport.model_validate_json(
            implementation_report_path.read_text(encoding="utf-8")
        )
        review_report = (
            ReviewReport.model_validate_json(review_report_path.read_text(encoding="utf-8"))
            if review_report_path
            else None
        )
        triage_reports = [
            TriageReport.model_validate_json(path.read_text(encoding="utf-8"))
            for path in triage_report_paths
        ]
    except (OSError, ValidationError, ValueError) as exc:
        raise VerificationStrengthError(
            f"could not load verification-strength inputs: {exc}"
        ) from exc

    implementation_report_path = implementation_report_path.resolve()
    command_results = _load_command_results(implementation_report.validation_results)
    signals: list[VerificationStrengthSignal] = []
    weak_patterns: list[WeakValidationPattern] = []
    score = 0

    status_signal, status_points = _implementation_status_signal(
        implementation_report_path, implementation_report
    )
    signals.append(status_signal)
    score += status_points
    if implementation_report.status != "proposed_diff":
        weak_patterns.append(
            _pattern(
                "implementation-not-proposed-diff",
                WeakPatternSeverity.ERROR,
                "Implementation did not produce a proposed diff",
                f"implementation status is {implementation_report.status}",
                implementation_report_path,
                (
                    f"status={implementation_report.status}; "
                    f"failure_reason={implementation_report.failure_reason}"
                ),
            )
        )

    validation_points = _validation_signals_and_patterns(
        implementation_report_path,
        implementation_report,
        command_results,
        signals,
        weak_patterns,
    )
    score += validation_points

    score += _acceptance_coverage_signals(
        task_contract_path.resolve(),
        task_contract,
        implementation_report,
        command_results,
        signals,
        weak_patterns,
    )
    score += _changed_file_relevance_signals(
        implementation_report_path,
        implementation_report,
        command_results,
        signals,
        weak_patterns,
    )
    score += _review_signals(
        review_report_path.resolve() if review_report_path else None,
        review_report,
        signals,
        weak_patterns,
    )
    score += _triage_signals(
        implementation_report_path,
        implementation_report,
        [path.resolve() for path in triage_report_paths],
        triage_reports,
        signals,
        weak_patterns,
    )
    score += _repository_signal(repository_map_path.resolve(), repository_map, signals)

    score = max(0, min(100, score))
    strength = _strength_level(score, weak_patterns)
    covered_acceptance = _covered_acceptance_criteria(
        task_contract, implementation_report, command_results
    )
    return VerificationStrengthReport(
        strength=strength,
        score=score,
        task_contract_path=task_contract_path.resolve(),
        repository_map_path=repository_map_path.resolve(),
        implementation_report_path=implementation_report_path,
        review_report_path=review_report_path.resolve() if review_report_path else None,
        triage_report_paths=[path.resolve() for path in triage_report_paths],
        changed_files=sorted(implementation_report.applied_files),
        validation_commands=sorted(
            {result.command_name for result in implementation_report.validation_results}
        ),
        assessed_acceptance_criteria=[item.text for item in task_contract.acceptance_criteria],
        covered_acceptance_criteria=covered_acceptance,
        signals=sorted(signals, key=lambda item: item.signal_id),
        weak_patterns=sorted(weak_patterns, key=lambda item: item.pattern_id),
        summary=_summary(strength, score, signals, weak_patterns),
    )


def write_verification_strength_report(report: VerificationStrengthReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_command_results(
    validation_results: list[ValidationResultSummary],
) -> dict[Path, CommandResult]:
    loaded: dict[Path, CommandResult] = {}
    for result in validation_results:
        path = result.result_path
        if path in loaded:
            continue
        try:
            loaded[path] = CommandResult.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError):
            continue
    return loaded


def _implementation_status_signal(
    implementation_report_path: Path, implementation_report: ImplementationReport
) -> tuple[VerificationStrengthSignal, int]:
    if implementation_report.status == "proposed_diff":
        return (
            _signal(
                "implementation-proposed-diff",
                VerificationSignalKind.POSITIVE,
                10,
                "Implementation reported a proposed diff",
                "implementation report reached proposed_diff status",
                implementation_report_path,
                f"status={implementation_report.status}",
            ),
            10,
        )
    return (
        _signal(
            "implementation-not-proposed-diff",
            VerificationSignalKind.NEGATIVE,
            -40,
            "Implementation did not report a proposed diff",
            f"implementation status is {implementation_report.status}",
            implementation_report_path,
            (
                f"status={implementation_report.status}; "
                f"failure_reason={implementation_report.failure_reason}"
            ),
        ),
        -40,
    )


def _validation_signals_and_patterns(
    implementation_report_path: Path,
    implementation_report: ImplementationReport,
    command_results: dict[Path, CommandResult],
    signals: list[VerificationStrengthSignal],
    weak_patterns: list[WeakValidationPattern],
) -> int:
    if not implementation_report.validation_results:
        signals.append(
            _signal(
                "validation-missing",
                VerificationSignalKind.NEGATIVE,
                -60,
                "Validation evidence is missing",
                "implementation report contains no validation results",
                implementation_report_path,
                "validation_results=[]",
            )
        )
        weak_patterns.append(
            _pattern(
                "no-validation",
                WeakPatternSeverity.ERROR,
                "No validation was reported",
                "verification strength cannot be established without validation results",
                implementation_report_path,
                "validation_results=[]",
            )
        )
        return -60

    points = 0
    latest_by_command = _latest_results_by_command(implementation_report.validation_results)
    passed_latest = [
        result
        for result in latest_by_command.values()
        if result.status == "passed" and result.classification.category == "passed"
    ]
    failed_latest = [
        result
        for result in latest_by_command.values()
        if result.status != "passed" or result.classification.category != "passed"
    ]
    if passed_latest:
        awarded = min(30, len(passed_latest) * 15)
        signals.append(
            _signal(
                "validation-passed-latest",
                VerificationSignalKind.POSITIVE,
                awarded,
                "Latest validation commands passed",
                f"{len(passed_latest)} latest validation command(s) passed",
                implementation_report_path,
                f"commands={sorted(result.command_name for result in passed_latest)}",
            )
        )
        points += awarded
    for result in failed_latest:
        signals.append(
            _signal(
                f"validation-latest-failed-{_slug(result.command_name)}",
                VerificationSignalKind.NEGATIVE,
                -60,
                "Latest validation command failed",
                f"{result.command_name} did not pass",
                implementation_report_path,
                (
                    f"command={result.command_name}; status={result.status}; "
                    f"classification={result.classification.category}; result={result.result_path}"
                ),
            )
        )
        weak_patterns.append(
            _pattern(
                f"failed-validation-{_slug(result.command_name)}",
                WeakPatternSeverity.ERROR,
                "Latest validation failed",
                "failed validation makes the assessment insufficient",
                implementation_report_path,
                (
                    f"command={result.command_name}; status={result.status}; "
                    f"classification={result.classification.category}"
                ),
            )
        )
        points -= 60
    retry_failures = len(implementation_report.validation_results) - len(passed_latest)
    if implementation_report.retry_decisions or retry_failures > len(failed_latest):
        signals.append(
            _signal(
                "validation-retry-history",
                VerificationSignalKind.INFO,
                -5,
                "Validation required retry evidence",
                "earlier failures or retry decisions reduce confidence in the final evidence",
                implementation_report_path,
                f"retry_decisions={len(implementation_report.retry_decisions)}",
            )
        )
        points -= 5
    if passed_latest and all(
        _is_smoke_validation(result, command_results) for result in passed_latest
    ):
        signals.append(
            _signal(
                "validation-smoke-only",
                VerificationSignalKind.NEGATIVE,
                -20,
                "Validation evidence is smoke-only",
                "all passing validation commands look like generic smoke/no-op checks",
                implementation_report_path,
                f"commands={sorted(result.command_name for result in passed_latest)}",
            )
        )
        weak_patterns.append(
            _pattern(
                "only-smoke-validation",
                WeakPatternSeverity.WARNING,
                "Only smoke validation passed",
                "smoke-only validation is weak evidence for task-specific behavior",
                implementation_report_path,
                f"commands={sorted(result.command_name for result in passed_latest)}",
            )
        )
        points -= 20
    elif passed_latest:
        signals.append(
            _signal(
                "validation-non-smoke-evidence",
                VerificationSignalKind.POSITIVE,
                20,
                "Validation includes non-smoke evidence",
                "at least one passing command appears task- or repository-specific",
                implementation_report_path,
                f"commands={sorted(result.command_name for result in passed_latest)}",
            )
        )
        points += 20
    return points


def _acceptance_coverage_signals(
    task_contract_path: Path,
    task_contract: TaskContract,
    implementation_report: ImplementationReport,
    command_results: dict[Path, CommandResult],
    signals: list[VerificationStrengthSignal],
    weak_patterns: list[WeakValidationPattern],
) -> int:
    if not task_contract.acceptance_criteria:
        signals.append(
            _signal(
                "acceptance-criteria-missing",
                VerificationSignalKind.NEGATIVE,
                -10,
                "Acceptance criteria are missing",
                "task contract has no explicit acceptance criteria",
                task_contract_path,
                "acceptance_criteria=[]",
            )
        )
        weak_patterns.append(
            _pattern(
                "missing-acceptance-criteria",
                WeakPatternSeverity.WARNING,
                "Acceptance criteria are missing",
                "validation strength cannot map evidence to criteria that are absent",
                task_contract_path,
                "acceptance_criteria=[]",
            )
        )
        return -10

    covered = _covered_acceptance_criteria(task_contract, implementation_report, command_results)
    if not covered:
        signals.append(
            _signal(
                "acceptance-coverage-missing",
                VerificationSignalKind.NEGATIVE,
                -20,
                "No acceptance criteria are referenced by evidence",
                "validation evidence does not share meaningful tokens with acceptance criteria",
                task_contract_path,
                f"acceptance_criteria={len(task_contract.acceptance_criteria)}",
            )
        )
        weak_patterns.append(
            _pattern(
                "missing-acceptance-coverage",
                WeakPatternSeverity.WARNING,
                "Acceptance coverage is missing",
                "no acceptance criterion has deterministic textual support in validation evidence",
                task_contract_path,
                f"acceptance_criteria={len(task_contract.acceptance_criteria)}",
            )
        )
        return -20

    if len(covered) == len(task_contract.acceptance_criteria):
        points = 20
        title = "All acceptance criteria are referenced"
    else:
        points = 10
        title = "Some acceptance criteria are referenced"
    signals.append(
        _signal(
            "acceptance-coverage-present",
            VerificationSignalKind.POSITIVE,
            points,
            title,
            (
                f"{len(covered)} of {len(task_contract.acceptance_criteria)} criteria "
                "have textual support"
            ),
            task_contract_path,
            f"covered={covered}",
        )
    )
    return points


def _changed_file_relevance_signals(
    implementation_report_path: Path,
    implementation_report: ImplementationReport,
    command_results: dict[Path, CommandResult],
    signals: list[VerificationStrengthSignal],
    weak_patterns: list[WeakValidationPattern],
) -> int:
    if not implementation_report.applied_files:
        return 0
    evidence = _validation_evidence_text(implementation_report, command_results)
    relevant = [
        path
        for path in implementation_report.applied_files
        if path.lower() in evidence or Path(path).name.lower() in evidence
    ]
    if relevant:
        signals.append(
            _signal(
                "changed-file-relevance",
                VerificationSignalKind.POSITIVE,
                15,
                "Validation evidence references changed files",
                "validation command metadata or excerpts mention changed file paths or names",
                implementation_report_path,
                f"changed_files={sorted(relevant)}",
            )
        )
        return 15
    signals.append(
        _signal(
            "validation-unrelated-to-changed-files",
            VerificationSignalKind.NEGATIVE,
            -15,
            "Validation evidence does not reference changed files",
            "no changed file path or basename appears in bounded validation evidence",
            implementation_report_path,
            f"changed_files={sorted(implementation_report.applied_files)}",
        )
    )
    weak_patterns.append(
        _pattern(
            "validation-unrelated-to-changed-files",
            WeakPatternSeverity.WARNING,
            "Validation appears unrelated to changed files",
            "bounded validation evidence does not mention files changed by the implementation",
            implementation_report_path,
            f"changed_files={sorted(implementation_report.applied_files)}",
        )
    )
    return -15


def _review_signals(
    review_report_path: Path | None,
    review_report: ReviewReport | None,
    signals: list[VerificationStrengthSignal],
    weak_patterns: list[WeakValidationPattern],
) -> int:
    if review_report is None or review_report_path is None:
        return 0
    findings = review_report.deterministic_findings + review_report.provider_findings
    error_count = sum(finding.severity == ReviewFindingSeverity.ERROR for finding in findings)
    warning_count = sum(finding.severity == ReviewFindingSeverity.WARNING for finding in findings)
    if review_report.outcome == "unacceptable" or error_count:
        signals.append(
            _signal(
                "review-unacceptable",
                VerificationSignalKind.NEGATIVE,
                -50,
                "Review outcome is unacceptable",
                "review report contains unacceptable findings",
                review_report_path,
                f"outcome={review_report.outcome}; error_findings={error_count}",
            )
        )
        weak_patterns.append(
            _pattern(
                "failed-review",
                WeakPatternSeverity.ERROR,
                "Review failed",
                "unacceptable review output prevents strong verification assessment",
                review_report_path,
                f"outcome={review_report.outcome}; error_findings={error_count}",
            )
        )
        return -50
    points = 10 if warning_count == 0 else 5
    signals.append(
        _signal(
            "review-acceptable",
            VerificationSignalKind.POSITIVE,
            points,
            "Review outcome is acceptable",
            "review report does not contain error findings",
            review_report_path,
            f"outcome={review_report.outcome}; warning_findings={warning_count}",
        )
    )
    return points


def _triage_signals(
    implementation_report_path: Path,
    implementation_report: ImplementationReport,
    triage_report_paths: list[Path],
    triage_reports: list[TriageReport],
    signals: list[VerificationStrengthSignal],
    weak_patterns: list[WeakValidationPattern],
) -> int:
    simulator_failures = [
        result
        for result in implementation_report.validation_results
        if result.classification.category
        in {
            VerificationFailureCategory.ASSERTION_TEST_FAILURE,
            VerificationFailureCategory.LINT_SYNTAX_FAILURE,
            VerificationFailureCategory.COMMAND_FAILURE,
        }
        and _looks_like_simulator_failure(result)
    ]
    if simulator_failures and not triage_reports:
        signals.append(
            _signal(
                "simulator-failure-without-triage",
                VerificationSignalKind.NEGATIVE,
                -10,
                "Simulator-like failure lacks triage",
                (
                    "failed validation evidence looks simulator-related but no triage "
                    "report was supplied"
                ),
                implementation_report_path,
                f"commands={sorted(result.command_name for result in simulator_failures)}",
            )
        )
        weak_patterns.append(
            _pattern(
                "missing-triage-for-simulator-failure",
                WeakPatternSeverity.WARNING,
                "Missing triage for simulator failure",
                "simulator/assertion failures should be paired with bounded triage artifacts",
                implementation_report_path,
                f"commands={sorted(result.command_name for result in simulator_failures)}",
            )
        )
        return -10
    if not triage_reports:
        return 0
    warnings = sum(len(report.warnings) for report in triage_reports)
    assertions = sum(len(report.assertion_failures) for report in triage_reports)
    points = 5 if warnings == 0 else 0
    signals.append(
        _signal(
            "triage-supplied",
            VerificationSignalKind.INFO,
            points,
            "Triage artifacts were supplied",
            "bounded triage reports are available for validation evidence",
            triage_report_paths[0],
            (
                f"triage_reports={len(triage_reports)}; warnings={warnings}; "
                f"assertion_failures={assertions}"
            ),
        )
    )
    return points


def _repository_signal(
    repository_map_path: Path,
    repository_map: RepositoryMap,
    signals: list[VerificationStrengthSignal],
) -> int:
    if repository_map.commands:
        signals.append(
            _signal(
                "repository-validation-context",
                VerificationSignalKind.INFO,
                5,
                "Repository map includes validation command context",
                "repository discovery found build or validation command evidence",
                repository_map_path,
                f"commands={len(repository_map.commands)}",
            )
        )
        return 5
    return 0


def _latest_results_by_command(
    validation_results: list[ValidationResultSummary],
) -> dict[str, ValidationResultSummary]:
    latest: dict[str, ValidationResultSummary] = {}
    for result in validation_results:
        latest[result.command_name] = result
    return latest


def _is_smoke_validation(
    result: ValidationResultSummary, command_results: dict[Path, CommandResult]
) -> bool:
    command_result = command_results.get(result.result_path)
    text_parts = [result.command_name]
    if command_result is not None:
        text_parts.extend(command_result.argv)
    text = " ".join(text_parts).lower()
    if any(token in text for token in ("pytest", "make", "verilator", "iverilog", "yosys")):
        return False
    return any(
        token in text
        for token in ("smoke", "noop", "no-op", "true", "echo ok", "python3 -c pass", "--help")
    )


def _covered_acceptance_criteria(
    task_contract: TaskContract,
    implementation_report: ImplementationReport,
    command_results: dict[Path, CommandResult],
) -> list[str]:
    evidence_tokens = _tokens(_validation_evidence_text(implementation_report, command_results))
    covered: list[str] = []
    for criterion in task_contract.acceptance_criteria:
        criterion_tokens = _tokens(criterion.text)
        if criterion_tokens and len(criterion_tokens & evidence_tokens) >= 1:
            covered.append(criterion.text)
    return sorted(covered)


def _validation_evidence_text(
    implementation_report: ImplementationReport,
    command_results: dict[Path, CommandResult],
) -> str:
    parts: list[str] = []
    for result in implementation_report.validation_results:
        parts.extend(
            [
                result.command_name,
                result.status,
                result.classification.category,
                result.classification.summary,
                " ".join(result.classification.evidence),
                " ".join(result.classification.stdout_excerpt),
                " ".join(result.classification.stderr_excerpt),
            ]
        )
        command_result = command_results.get(result.result_path)
        if command_result is not None:
            parts.extend(command_result.argv)
            parts.append(str(command_result.cwd))
    return " ".join(parts).lower()


def _looks_like_simulator_failure(result: ValidationResultSummary) -> bool:
    text = " ".join(
        [
            result.command_name,
            result.classification.summary,
            " ".join(result.classification.evidence),
            " ".join(result.classification.stdout_excerpt),
            " ".join(result.classification.stderr_excerpt),
        ]
    ).lower()
    return any(
        token in text
        for token in (
            "assert",
            "verilator",
            "iverilog",
            "vvp",
            "vcs",
            "questa",
            "xcelium",
            "vsim",
            "vcd",
            "fst",
            "waveform",
            "simulation",
        )
    )


def _strength_level(
    score: int, weak_patterns: list[WeakValidationPattern]
) -> VerificationStrengthLevel:
    if any(pattern.severity == WeakPatternSeverity.ERROR for pattern in weak_patterns):
        return VerificationStrengthLevel.INSUFFICIENT
    if score >= 80 and not weak_patterns:
        return VerificationStrengthLevel.STRONG
    if score >= 60:
        return VerificationStrengthLevel.MODERATE
    return VerificationStrengthLevel.WEAK


def _summary(
    strength: VerificationStrengthLevel,
    score: int,
    signals: list[VerificationStrengthSignal],
    weak_patterns: list[WeakValidationPattern],
) -> str:
    return (
        f"{strength} verification strength with score {score}/100, "
        f"{len(signals)} signal(s), and {len(weak_patterns)} weak pattern(s)"
    )


def _signal(
    signal_id: str,
    kind: VerificationSignalKind,
    points: int,
    title: str,
    description: str,
    artifact: Path,
    detail: str,
) -> VerificationStrengthSignal:
    return VerificationStrengthSignal(
        signal_id=signal_id,
        kind=kind,
        points=points,
        title=title,
        description=description,
        evidence=[EvidenceCitation(artifact=artifact, detail=detail)],
    )


def _pattern(
    pattern_id: str,
    severity: WeakPatternSeverity,
    title: str,
    description: str,
    artifact: Path,
    detail: str,
) -> WeakValidationPattern:
    return WeakValidationPattern(
        pattern_id=pattern_id,
        severity=severity,
        title=title,
        description=description,
        evidence=[EvidenceCitation(artifact=artifact, detail=detail)],
    )


def _tokens(text: str) -> set[str]:
    stopwords = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "file",
        "contains",
        "should",
        "must",
        "validation",
        "command",
        "test",
        "check",
        "rtl",
        "sv",
    }
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9_]+", text.lower())
        if len(token) >= 3 and token not in stopwords
    }


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "item"
