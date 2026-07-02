from __future__ import annotations

import json
from pathlib import Path

import pytest

from rtl_agent.artifacts import RunStore
from rtl_agent.config import AgentConfig, CommandConfig
from rtl_agent.discovery import discover_repository, write_repository_map
from rtl_agent.implementation import run_bounded_implementation, write_implementation_report
from rtl_agent.issues import parse_issue_file, write_task_contract
from rtl_agent.review import ReviewError, review_implementation, write_review_report


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_review_inputs(
    tmp_path: Path, validation_assertion: str = "'new_signal' in Path('rtl/top.sv').read_text()"
) -> tuple[Path, Path, Path, Path]:
    repo = tmp_path / "repo"
    write(repo / "rtl" / "top.sv", "module top;\n  wire old_signal;\nendmodule\n")
    issue = tmp_path / "issue.md"
    write(
        issue,
        """# Rename signal

## Requested Behavior
- Rename `rtl/top.sv` old signal text.

## Scope
- `rtl/top.sv`

## Acceptance Criteria
- File contains new signal text.

## Validation Commands
```bash
python3 -c check
```

## Prohibited Shortcuts
- Do not delete rtl/top.sv

## Evidence Requirements
- Report validation results.
""",
    )
    repository_map = discover_repository(repo)
    repository_map_path = tmp_path / "repository-map.json"
    write_repository_map(repository_map, repository_map_path)
    task_contract = parse_issue_file(issue, repository_map_path)
    task_contract_path = tmp_path / "task-contract.json"
    write_task_contract(task_contract, task_contract_path)
    config = AgentConfig(
        repository_path=repo,
        run_artifact_dir=tmp_path / ".rtl-agent" / "runs",
        allowed_working_paths=[repo],
        commands={
            "check": CommandConfig(
                argv=[
                    "python3",
                    "-c",
                    f"from pathlib import Path; assert {validation_assertion}",
                ],
                cwd=repo,
            )
        },
    )
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "responses": [
                    {
                        "message": "Apply exact replacement and validate.",
                        "tool_calls": [
                            {
                                "tool": "replace_text",
                                "path": "rtl/top.sv",
                                "old": "old_signal",
                                "new": "new_signal",
                            }
                        ],
                        "validation_commands": ["check"],
                        "stop": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    store = RunStore(config.run_root, run_id="run-1")
    store.create()
    implementation = run_bounded_implementation(
        config=config,
        run_store=store,
        provider_plan=plan,
        task_contract_path=task_contract_path,
        repository_map_path=repository_map_path,
        allowed_files=["rtl/top.sv"],
        allowed_validation_commands=["check"],
        max_iterations=1,
    )
    implementation_report_path = store.run_dir / "implementation" / "report.json"
    write_implementation_report(implementation, implementation_report_path)
    return task_contract_path, repository_map_path, implementation_report_path, repo


def test_review_accepts_passed_in_scope_report(tmp_path: Path) -> None:
    task_contract_path, repository_map_path, implementation_report_path, _repo = make_review_inputs(
        tmp_path
    )

    report = review_implementation(
        task_contract_path=task_contract_path,
        repository_map_path=repository_map_path,
        implementation_report_path=implementation_report_path,
    )

    assert report.outcome == "acceptable"
    assert report.deterministic_findings == []
    assert report.provider_findings == []
    assert report.checked_files == ["rtl/top.sv"]
    assert report.checked_acceptance_criteria == ["File contains new signal text."]


def test_review_rejects_failed_validation(tmp_path: Path) -> None:
    task_contract_path, repository_map_path, implementation_report_path, _repo = make_review_inputs(
        tmp_path, validation_assertion="'missing_signal' in Path('rtl/top.sv').read_text()"
    )

    report = review_implementation(
        task_contract_path=task_contract_path,
        repository_map_path=repository_map_path,
        implementation_report_path=implementation_report_path,
    )

    assert report.outcome == "unacceptable"
    assert any(
        finding.finding_id.startswith("det-status") for finding in report.deterministic_findings
    )
    assert any(
        finding.finding_id.startswith("det-validation-failed")
        for finding in report.deterministic_findings
    )


def test_review_warns_on_retried_validation_failure_with_later_pass(tmp_path: Path) -> None:
    task_contract_path, repository_map_path, implementation_report_path, _repo = make_review_inputs(
        tmp_path
    )
    data = json.loads(implementation_report_path.read_text(encoding="utf-8"))
    failed = dict(data["validation_results"][0])
    failed["status"] = "failed"
    failed["exit_code"] = 1
    failed["classification"] = {
        "category": "assertion_or_test_failure",
        "summary": "assertion or test failure evidence detected",
        "evidence": ["stderr: AssertionError"],
        "stdout_excerpt": [],
        "stderr_excerpt": ["AssertionError"],
    }
    data["validation_results"] = [failed, data["validation_results"][0]]
    implementation_report_path.write_text(json.dumps(data), encoding="utf-8")

    report = review_implementation(
        task_contract_path=task_contract_path,
        repository_map_path=repository_map_path,
        implementation_report_path=implementation_report_path,
    )

    assert report.outcome == "acceptable"
    assert any(
        finding.finding_id == "det-validation-failed-1" and finding.severity == "warning"
        for finding in report.deterministic_findings
    )


def test_review_requires_validation_evidence(tmp_path: Path) -> None:
    task_contract_path, repository_map_path, implementation_report_path, _repo = make_review_inputs(
        tmp_path
    )
    data = json.loads(implementation_report_path.read_text(encoding="utf-8"))
    data["validation_results"] = []
    implementation_report_path.write_text(json.dumps(data), encoding="utf-8")

    report = review_implementation(
        task_contract_path=task_contract_path,
        repository_map_path=repository_map_path,
        implementation_report_path=implementation_report_path,
    )

    assert report.outcome == "unacceptable"
    assert any(
        finding.finding_id == "det-validation-missing" for finding in report.deterministic_findings
    )


def test_review_rejects_provider_findings_without_cited_evidence(tmp_path: Path) -> None:
    task_contract_path, repository_map_path, implementation_report_path, _repo = make_review_inputs(
        tmp_path
    )
    provider_findings = tmp_path / "provider-findings.json"
    provider_findings.write_text(
        json.dumps(
            {
                "findings": [
                    {
                        "finding_id": "provider-risk",
                        "source": "provider",
                        "severity": "warning",
                        "title": "Uncited risk",
                        "description": "This has no evidence and must be rejected.",
                        "evidence": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ReviewError, match="could not load provider findings"):
        review_implementation(
            task_contract_path=task_contract_path,
            repository_map_path=repository_map_path,
            implementation_report_path=implementation_report_path,
            provider_findings_path=provider_findings,
        )


def test_review_persists_stable_json(tmp_path: Path) -> None:
    task_contract_path, repository_map_path, implementation_report_path, _repo = make_review_inputs(
        tmp_path
    )
    report = review_implementation(
        task_contract_path, repository_map_path, implementation_report_path
    )
    first = tmp_path / "first-review.json"
    second = tmp_path / "second-review.json"

    write_review_report(report, first)
    write_review_report(report, second)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    assert json.loads(first.read_text(encoding="utf-8"))["schema_version"] == 1
