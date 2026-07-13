from __future__ import annotations

import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from _example_check import ROOT

from rtl_agent.implementation_models import (
    ImplementationReport,
    ImplementationStatus,
    ToolName,
    ToolResult,
    ValidationResultSummary,
    VerificationClassification,
    VerificationFailureCategory,
)
from rtl_agent.repository_map import (
    DeclarationKind,
    FileCategory,
    FileRecord,
    GitMetadata,
    HierarchyInfo,
    RepositoryMap,
    ScanStatistics,
    SourceDeclaration,
    SourceFileInfo,
)
from rtl_agent.review import review_implementation
from rtl_agent.review_models import ReviewFindingSeverity, ReviewOutcome, ReviewReport
from rtl_agent.task_contract import (
    IssueReference,
    ParsedRequirement,
    RepositoryMapContext,
    RequirementSource,
    TaskContract,
    ValidationCommand,
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_model(path: Path, model: Any) -> None:
    _write_json(path, model.model_dump(mode="json"))


def _repository_map(repo: Path) -> RepositoryMap:
    return RepositoryMap(
        tool_version="example-check",
        repository_root=repo,
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
        git=GitMetadata(is_git_repository=False),
        scan_statistics=ScanStatistics(files_seen=1, files_indexed=1, relevant_files=1),
        files=[
            FileRecord(
                path="rtl/top.sv",
                categories=[FileCategory.RTL_SOURCE],
                size_bytes=len("module top; endmodule\n"),
                source=SourceFileInfo(
                    declarations=[
                        SourceDeclaration(kind=DeclarationKind.MODULE, name="top", line=1)
                    ]
                ),
            )
        ],
        hierarchy=HierarchyInfo(),
        commands=[],
        guidance=[],
    )


def _task_contract(task_contract_path: Path, repository_map_path: Path, repo: Path) -> TaskContract:
    return TaskContract(
        tool_version="example-check",
        issue_path=task_contract_path.parent / "issue.md",
        repository_map=RepositoryMapContext(
            path=repository_map_path,
            schema_version=1,
            repository_root=repo,
            file_count=1,
            command_count=0,
            matched_paths=["rtl/top.sv"],
        ),
        title="Keep top module intact",
        requested_behavior=[
            ParsedRequirement(
                text="Preserve rtl/top.sv while adding harmless comments.",
                line=3,
                source=RequirementSource.HEADING,
            )
        ],
        scoped_repository_context=[
            IssueReference(
                value="rtl/top.sv",
                kind="path",
                line=6,
                in_repository_map=True,
            )
        ],
        acceptance_criteria=[
            ParsedRequirement(
                text="The top module remains present.",
                line=9,
                source=RequirementSource.CHECKLIST,
            )
        ],
        validation_commands=[
            ValidationCommand(
                command=["python3", "-c", "pass"],
                raw="python3 -c pass",
                line=12,
                source=RequirementSource.FENCED_BLOCK,
            )
        ],
        prohibited_shortcuts=[
            ParsedRequirement(
                text="Do not delete rtl/top.sv",
                line=15,
                source=RequirementSource.CHECKLIST,
            )
        ],
        evidence_requirements=[
            ParsedRequirement(
                text="Report validation results.",
                line=18,
                source=RequirementSource.CHECKLIST,
            )
        ],
    )


def _implementation_report(
    *,
    repo: Path,
    task_contract_path: Path,
    repository_map_path: Path,
    diff_path: Path,
    command_dir: Path,
) -> ImplementationReport:
    command_dir.mkdir(parents=True, exist_ok=True)
    result_path = command_dir / "check.json"
    stdout_path = command_dir / "check.stdout"
    stderr_path = command_dir / "check.stderr"
    _write_json(
        result_path,
        {
            "command": ["python3", "-c", "pass"],
            "cwd": str(repo),
            "exit_code": 0,
            "status": "passed",
        },
    )
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    return ImplementationReport(
        status=ImplementationStatus.PROPOSED_DIFF,
        task_contract_path=task_contract_path,
        repository_map_path=repository_map_path,
        repository_root=repo,
        provider="example-check",
        iterations=1,
        allowed_files=["rtl/top.sv"],
        allowed_validation_commands=["check"],
        applied_files=["rtl/top.sv"],
        tool_results=[
            ToolResult(
                tool=ToolName.REPLACE_TEXT,
                path="rtl/top.sv",
                status="applied",
                message="example diff artifact supplied by check",
            )
        ],
        validation_results=[
            ValidationResultSummary(
                command_name="check",
                status="passed",
                exit_code=0,
                result_path=result_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                classification=VerificationClassification(
                    category=VerificationFailureCategory.PASSED,
                    summary="command passed",
                ),
            )
        ],
        diff_path=diff_path,
    )


def _review_with_diff(workspace: Path, diff_text: str, label: str) -> ReviewReport:
    repo = workspace / label / "repo"
    (repo / "rtl").mkdir(parents=True)
    (repo / "rtl" / "top.sv").write_text("module top; endmodule\n", encoding="utf-8")

    repository_map_path = workspace / label / "repository-map.json"
    task_contract_path = workspace / label / "task-contract.json"
    implementation_report_path = workspace / label / "implementation" / "report.json"
    diff_path = workspace / label / "implementation" / "diff.patch"

    _write_model(repository_map_path, _repository_map(repo))
    _write_model(task_contract_path, _task_contract(task_contract_path, repository_map_path, repo))
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_path.write_text(diff_text, encoding="utf-8")
    _write_model(
        implementation_report_path,
        _implementation_report(
            repo=repo,
            task_contract_path=task_contract_path,
            repository_map_path=repository_map_path,
            diff_path=diff_path,
            command_dir=workspace / label / "commands",
        ),
    )

    return review_implementation(
        task_contract_path=task_contract_path,
        repository_map_path=repository_map_path,
        implementation_report_path=implementation_report_path,
    )


def main() -> int:
    assert ROOT.exists()
    with tempfile.TemporaryDirectory(prefix="rtl-agent-prohibited-shortcut-review-") as raw_tmp:
        workspace = Path(raw_tmp)
        conflicting = _review_with_diff(
            workspace,
            "\n".join(
                [
                    "diff --git a/rtl/top.sv b/rtl/top.sv",
                    "--- a/rtl/top.sv",
                    "+++ b/rtl/top.sv",
                    "@@ -1 +1,2 @@",
                    " module top; endmodule",
                    "+// delete rtl/top.sv",
                    "",
                ]
            ),
            "conflicting",
        )
        prohibited_findings = [
            finding
            for finding in conflicting.deterministic_findings
            if finding.finding_id.startswith("det-prohibited-shortcut-")
        ]
        assert conflicting.outcome == ReviewOutcome.UNACCEPTABLE
        assert len(prohibited_findings) == 1
        finding = prohibited_findings[0]
        assert finding.finding_id == "det-prohibited-shortcut-1"
        assert finding.severity == ReviewFindingSeverity.ERROR
        assert finding.description == "Do not delete rtl/top.sv"
        assert len(finding.evidence) == 1
        assert (
            finding.evidence[0].artifact
            == (workspace / "conflicting" / "task-contract.json").resolve()
        )
        assert finding.evidence[0].detail == "matched prohibited token in diff: delete rtl/top.sv"

        clean = _review_with_diff(
            workspace,
            "\n".join(
                [
                    "diff --git a/rtl/top.sv b/rtl/top.sv",
                    "--- a/rtl/top.sv",
                    "+++ b/rtl/top.sv",
                    "@@ -1 +1,2 @@",
                    " module top; endmodule",
                    "+// implementation note: top remains present",
                    "",
                ]
            ),
            "clean",
        )
        assert clean.outcome == ReviewOutcome.ACCEPTABLE
        assert not any(
            finding.finding_id.startswith("det-prohibited-shortcut-")
            for finding in clean.deterministic_findings
        )
        assert clean.deterministic_findings == []

    print("prohibited-shortcut review example check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
