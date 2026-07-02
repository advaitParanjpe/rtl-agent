from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import ValidationError

from rtl_agent.implementation_models import ImplementationReport
from rtl_agent.repository_map import RepositoryMap
from rtl_agent.review_models import (
    EvidenceCitation,
    ReviewFinding,
    ReviewFindingSeverity,
    ReviewFindingSource,
    ReviewOutcome,
    ReviewReport,
)
from rtl_agent.task_contract import TaskContract


class ReviewError(RuntimeError):
    pass


def review_implementation(
    task_contract_path: Path,
    repository_map_path: Path,
    implementation_report_path: Path,
    provider_findings_path: Path | None = None,
) -> ReviewReport:
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
    except (OSError, ValidationError, ValueError) as exc:
        raise ReviewError(f"could not load review inputs: {exc}") from exc

    deterministic_findings = _deterministic_findings(
        task_contract_path=task_contract_path.resolve(),
        repository_map_path=repository_map_path.resolve(),
        implementation_report_path=implementation_report_path.resolve(),
        task_contract=task_contract,
        repository_map=repository_map,
        implementation_report=implementation_report,
    )
    provider_findings = _load_provider_findings(provider_findings_path)
    all_findings = deterministic_findings + provider_findings
    outcome = (
        ReviewOutcome.UNACCEPTABLE
        if any(finding.severity == ReviewFindingSeverity.ERROR for finding in all_findings)
        else ReviewOutcome.ACCEPTABLE
    )
    diff_path = (
        implementation_report.diff_path.resolve() if implementation_report.diff_path else None
    )
    return ReviewReport(
        outcome=outcome,
        task_contract_path=task_contract_path.resolve(),
        repository_map_path=repository_map_path.resolve(),
        implementation_report_path=implementation_report_path.resolve(),
        diff_path=diff_path,
        deterministic_findings=deterministic_findings,
        provider_findings=provider_findings,
        checked_acceptance_criteria=[item.text for item in task_contract.acceptance_criteria],
        checked_files=implementation_report.applied_files,
        summary=_summary(outcome, deterministic_findings, provider_findings),
    )


def write_review_report(report: ReviewReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _deterministic_findings(
    task_contract_path: Path,
    repository_map_path: Path,
    implementation_report_path: Path,
    task_contract: TaskContract,
    repository_map: RepositoryMap,
    implementation_report: ImplementationReport,
) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    findings.extend(
        _status_and_validation_findings(implementation_report_path, implementation_report)
    )
    findings.extend(
        _scope_findings(
            task_contract_path,
            repository_map_path,
            implementation_report_path,
            task_contract,
            repository_map,
            implementation_report,
        )
    )
    findings.extend(
        _diff_findings(
            task_contract_path, implementation_report_path, task_contract, implementation_report
        )
    )
    findings.extend(_acceptance_findings(task_contract_path, task_contract, implementation_report))
    return sorted(findings, key=lambda finding: finding.finding_id)


def _status_and_validation_findings(
    implementation_report_path: Path, implementation_report: ImplementationReport
) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    if implementation_report.status != "proposed_diff":
        findings.append(
            _finding(
                "det-status-not-proposed-diff",
                ReviewFindingSeverity.ERROR,
                "Implementation did not produce an acceptable proposed diff",
                f"implementation status is {implementation_report.status}",
                implementation_report_path,
                (
                    f"status={implementation_report.status}; "
                    f"failure_reason={implementation_report.failure_reason}"
                ),
            )
        )
    if not implementation_report.validation_results:
        findings.append(
            _finding(
                "det-validation-missing",
                ReviewFindingSeverity.ERROR,
                "Validation evidence is missing",
                "implementation report contains no validation results",
                implementation_report_path,
                "validation_results=[]",
            )
        )
    latest_by_command = {
        result.command_name: index
        for index, result in enumerate(implementation_report.validation_results, start=1)
    }
    for index, result in enumerate(implementation_report.validation_results, start=1):
        if result.status != "passed" or result.classification.category != "passed":
            severity = (
                ReviewFindingSeverity.ERROR
                if latest_by_command[result.command_name] == index
                else ReviewFindingSeverity.WARNING
            )
            findings.append(
                _finding(
                    f"det-validation-failed-{index}",
                    severity,
                    "Validation attempt did not pass",
                    f"{result.command_name} ended with status {result.status}",
                    implementation_report_path,
                    (
                        f"command={result.command_name}; status={result.status}; "
                        f"classification={result.classification.category}; "
                        f"result={result.result_path}"
                    ),
                )
            )
    return findings


def _scope_findings(
    task_contract_path: Path,
    repository_map_path: Path,
    implementation_report_path: Path,
    task_contract: TaskContract,
    repository_map: RepositoryMap,
    implementation_report: ImplementationReport,
) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    scoped_paths = {
        reference.value
        for reference in task_contract.scoped_repository_context
        if reference.in_repository_map is not False
    }
    known_paths = {record.path for record in repository_map.files}
    for path in implementation_report.applied_files:
        if path not in scoped_paths:
            findings.append(
                _finding(
                    f"det-out-of-scope-{_slug(path)}",
                    ReviewFindingSeverity.ERROR,
                    "Edited file is outside task scope",
                    f"{path} is not listed in task-contract scope",
                    task_contract_path,
                    f"applied_file={path}; scoped_paths={sorted(scoped_paths)}",
                )
            )
        if path not in known_paths:
            findings.append(
                _finding(
                    f"det-unknown-file-{_slug(path)}",
                    ReviewFindingSeverity.ERROR,
                    "Edited file is missing from repository map",
                    f"{path} does not appear in repository-map files",
                    repository_map_path,
                    f"applied_file={path}",
                )
            )
    if not implementation_report.applied_files:
        findings.append(
            _finding(
                "det-no-applied-files",
                ReviewFindingSeverity.ERROR,
                "No applied files were reported",
                "implementation report has no applied files",
                implementation_report_path,
                "applied_files=[]",
            )
        )
    return findings


def _diff_findings(
    task_contract_path: Path,
    implementation_report_path: Path,
    task_contract: TaskContract,
    implementation_report: ImplementationReport,
) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    if implementation_report.applied_files and implementation_report.diff_path is None:
        return [
            _finding(
                "det-diff-missing",
                ReviewFindingSeverity.ERROR,
                "Diff artifact is missing",
                "implementation report has applied files but no diff path",
                implementation_report_path,
                "diff_path=null",
            )
        ]
    if implementation_report.diff_path is None:
        return findings
    diff_path = implementation_report.diff_path
    if not diff_path.exists():
        return [
            _finding(
                "det-diff-path-missing",
                ReviewFindingSeverity.ERROR,
                "Diff artifact path does not exist",
                "implementation report points to a missing diff artifact",
                implementation_report_path,
                f"diff_path={diff_path}",
            )
        ]
    try:
        diff_text = diff_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [
            _finding(
                "det-diff-unreadable",
                ReviewFindingSeverity.ERROR,
                "Diff artifact is unreadable",
                f"could not read diff artifact: {exc}",
                diff_path,
                str(exc),
            )
        ]
    for index, shortcut in enumerate(task_contract.prohibited_shortcuts, start=1):
        conflict_token = _prohibited_token(shortcut.text)
        if conflict_token and conflict_token in diff_text.lower():
            findings.append(
                _finding(
                    f"det-prohibited-shortcut-{index}",
                    ReviewFindingSeverity.ERROR,
                    "Diff appears to conflict with a prohibited shortcut",
                    shortcut.text,
                    task_contract_path,
                    f"matched prohibited token in diff: {conflict_token}",
                )
            )
    return findings


def _acceptance_findings(
    task_contract_path: Path,
    task_contract: TaskContract,
    implementation_report: ImplementationReport,
) -> list[ReviewFinding]:
    if task_contract.acceptance_criteria and implementation_report.validation_results:
        return []
    if not task_contract.acceptance_criteria:
        return [
            _finding(
                "det-acceptance-criteria-missing",
                ReviewFindingSeverity.WARNING,
                "Acceptance criteria are missing",
                "task contract has no acceptance criteria to check",
                task_contract_path,
                "acceptance_criteria=[]",
            )
        ]
    return []


def _load_provider_findings(provider_findings_path: Path | None) -> list[ReviewFinding]:
    if provider_findings_path is None:
        return []
    try:
        raw = json.loads(provider_findings_path.read_text(encoding="utf-8"))
        items = raw.get("findings", raw if isinstance(raw, list) else [])
        if not isinstance(items, list):
            raise ValueError("provider findings must be a list or mapping with findings")
        findings = [ReviewFinding.model_validate(item) for item in items]
    except (OSError, ValidationError, ValueError, json.JSONDecodeError) as exc:
        raise ReviewError(f"could not load provider findings: {exc}") from exc
    for finding in findings:
        if finding.source != ReviewFindingSource.PROVIDER:
            raise ReviewError("provider-backed findings must use source='provider'")
    return sorted(findings, key=lambda finding: finding.finding_id)


def _finding(
    finding_id: str,
    severity: ReviewFindingSeverity,
    title: str,
    description: str,
    artifact: Path,
    detail: str,
) -> ReviewFinding:
    return ReviewFinding(
        finding_id=finding_id,
        source=ReviewFindingSource.DETERMINISTIC,
        severity=severity,
        title=title,
        description=description,
        evidence=[EvidenceCitation(artifact=artifact, detail=detail)],
    )


def _summary(
    outcome: ReviewOutcome,
    deterministic_findings: list[ReviewFinding],
    provider_findings: list[ReviewFinding],
) -> str:
    error_count = sum(
        finding.severity == ReviewFindingSeverity.ERROR
        for finding in deterministic_findings + provider_findings
    )
    return (
        f"{outcome} with {error_count} error finding(s), "
        f"{len(deterministic_findings)} deterministic finding(s), "
        f"and {len(provider_findings)} provider finding(s)"
    )


def _prohibited_token(text: str) -> str | None:
    lowered = text.lower()
    lowered = re.sub(r"^do not\s+", "", lowered).strip()
    lowered = re.sub(r"[^a-z0-9_./ -]+", "", lowered)
    words = [word for word in lowered.split() if len(word) > 2]
    if not words:
        return None
    return " ".join(words[:4])


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "item"
