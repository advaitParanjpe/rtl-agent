from __future__ import annotations

import json
from pathlib import Path

import pytest

from rtl_agent.artifacts import RunStore
from rtl_agent.config import AgentConfig, CommandConfig
from rtl_agent.discovery import discover_repository, write_repository_map
from rtl_agent.implementation import ImplementationError, run_bounded_implementation
from rtl_agent.issues import parse_issue_file, write_task_contract


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_repo_inputs(tmp_path: Path) -> tuple[AgentConfig, Path, Path, Path]:
    repo = tmp_path / "repo"
    write(repo / "rtl" / "top.sv", "module top;\n  wire old_signal;\nendmodule\n")
    write(
        tmp_path / "issue.md",
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

## Evidence Requirements
- Report validation results.
""",
    )
    repository_map = discover_repository(repo)
    repository_map_path = tmp_path / "repository-map.json"
    write_repository_map(repository_map, repository_map_path)
    task_contract = parse_issue_file(tmp_path / "issue.md", repository_map_path)
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
                    "from pathlib import Path; "
                    "assert 'new_signal' in Path('rtl/top.sv').read_text()",
                ],
                cwd=repo,
            )
        },
    )
    return config, repository_map_path, task_contract_path, repo


def write_plan(path: Path, data: dict[str, object]) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_bounded_implementation_applies_edit_and_runs_named_validation(tmp_path: Path) -> None:
    config, repository_map_path, task_contract_path, repo = make_repo_inputs(tmp_path)
    plan = write_plan(
        tmp_path / "plan.json",
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
        },
    )
    store = RunStore(config.run_root, run_id="run-1")
    store.create()

    report = run_bounded_implementation(
        config=config,
        run_store=store,
        provider_plan=plan,
        task_contract_path=task_contract_path,
        repository_map_path=repository_map_path,
        allowed_files=["rtl/top.sv"],
        allowed_validation_commands=["check"],
        max_iterations=1,
    )

    assert report.status == "proposed_diff"
    assert report.applied_files == ["rtl/top.sv"]
    assert report.validation_results[0].status == "passed"
    assert "new_signal" in (repo / "rtl" / "top.sv").read_text(encoding="utf-8")
    assert report.diff_path is not None
    assert report.diff_path.exists()
    assert (store.run_dir / "implementation" / "provider-request-1.json").exists()
    assert (store.run_dir / "implementation" / "provider-response-1.json").exists()


def test_bounded_implementation_rejects_unscoped_allowed_file(tmp_path: Path) -> None:
    config, repository_map_path, task_contract_path, _repo = make_repo_inputs(tmp_path)
    write(config.repository_root / "rtl" / "other.sv", "module other; endmodule\n")
    repository_map = discover_repository(config.repository_root)
    write_repository_map(repository_map, repository_map_path)
    plan = write_plan(tmp_path / "plan.json", {"responses": [{"message": "unused"}]})
    store = RunStore(config.run_root, run_id="run-1")
    store.create()

    with pytest.raises(ImplementationError, match="outside task scope"):
        run_bounded_implementation(
            config=config,
            run_store=store,
            provider_plan=plan,
            task_contract_path=task_contract_path,
            repository_map_path=repository_map_path,
            allowed_files=["rtl/other.sv"],
            allowed_validation_commands=[],
            max_iterations=1,
        )


def test_bounded_implementation_reports_disallowed_validation_command(tmp_path: Path) -> None:
    config, repository_map_path, task_contract_path, _repo = make_repo_inputs(tmp_path)
    plan = write_plan(
        tmp_path / "plan.json",
        {
            "responses": [
                {
                    "message": "Ask for disallowed command.",
                    "tool_calls": [],
                    "validation_commands": ["check"],
                    "stop": True,
                }
            ]
        },
    )
    store = RunStore(config.run_root, run_id="run-1")
    store.create()

    report = run_bounded_implementation(
        config=config,
        run_store=store,
        provider_plan=plan,
        task_contract_path=task_contract_path,
        repository_map_path=repository_map_path,
        allowed_files=["rtl/top.sv"],
        allowed_validation_commands=[],
        max_iterations=1,
    )

    assert report.status == "failed"
    assert report.failure_reason == "validation command is not allowed: check"


def test_bounded_implementation_rejects_tool_call_for_unallowed_file(tmp_path: Path) -> None:
    config, repository_map_path, task_contract_path, _repo = make_repo_inputs(tmp_path)
    plan = write_plan(
        tmp_path / "plan.json",
        {
            "responses": [
                {
                    "message": "Try another file.",
                    "tool_calls": [
                        {
                            "tool": "replace_text",
                            "path": "rtl/other.sv",
                            "old": "x",
                            "new": "y",
                        }
                    ],
                    "stop": True,
                }
            ]
        },
    )
    store = RunStore(config.run_root, run_id="run-1")
    store.create()

    report = run_bounded_implementation(
        config=config,
        run_store=store,
        provider_plan=plan,
        task_contract_path=task_contract_path,
        repository_map_path=repository_map_path,
        allowed_files=["rtl/top.sv"],
        allowed_validation_commands=[],
        max_iterations=1,
    )

    assert report.status == "failed"
    assert report.failure_reason == "file is not explicitly allowed: rtl/other.sv"


def test_bounded_implementation_retries_after_failed_validation(tmp_path: Path) -> None:
    config, repository_map_path, task_contract_path, repo = make_repo_inputs(tmp_path)
    plan = write_plan(
        tmp_path / "plan.json",
        {
            "responses": [
                {
                    "message": "Apply first attempt.",
                    "tool_calls": [
                        {
                            "tool": "replace_text",
                            "path": "rtl/top.sv",
                            "old": "old_signal",
                            "new": "bad_signal",
                        }
                    ],
                    "validation_commands": ["check"],
                    "stop": True,
                },
                {
                    "message": "Fix failed validation.",
                    "tool_calls": [
                        {
                            "tool": "replace_text",
                            "path": "rtl/top.sv",
                            "old": "bad_signal",
                            "new": "new_signal",
                        }
                    ],
                    "validation_commands": ["check"],
                    "stop": True,
                },
            ]
        },
    )
    store = RunStore(config.run_root, run_id="run-1")
    store.create()

    report = run_bounded_implementation(
        config=config,
        run_store=store,
        provider_plan=plan,
        task_contract_path=task_contract_path,
        repository_map_path=repository_map_path,
        allowed_files=["rtl/top.sv"],
        allowed_validation_commands=["check"],
        max_iterations=2,
    )

    assert report.status == "proposed_diff"
    assert [item.status for item in report.validation_results] == ["failed", "passed"]
    assert report.validation_results[0].classification.category == "assertion_or_test_failure"
    assert report.retry_decisions[0].decision == "retry"
    assert "new_signal" in (repo / "rtl" / "top.sv").read_text(encoding="utf-8")
    request_2 = json.loads(
        (store.run_dir / "implementation" / "provider-request-2.json").read_text(encoding="utf-8")
    )
    assert request_2["failure_evidence"][0]["category"] == "assertion_or_test_failure"
    assert "Traceback" not in json.dumps(request_2["failure_evidence"])


def test_bounded_implementation_stays_failed_when_retry_limit_reached(tmp_path: Path) -> None:
    config, repository_map_path, task_contract_path, _repo = make_repo_inputs(tmp_path)
    plan = write_plan(
        tmp_path / "plan.json",
        {
            "responses": [
                {
                    "message": "Apply bad edit.",
                    "tool_calls": [
                        {
                            "tool": "replace_text",
                            "path": "rtl/top.sv",
                            "old": "old_signal",
                            "new": "bad_signal",
                        }
                    ],
                    "validation_commands": ["check"],
                    "stop": True,
                }
            ]
        },
    )
    store = RunStore(config.run_root, run_id="run-1")
    store.create()

    report = run_bounded_implementation(
        config=config,
        run_store=store,
        provider_plan=plan,
        task_contract_path=task_contract_path,
        repository_map_path=repository_map_path,
        allowed_files=["rtl/top.sv"],
        allowed_validation_commands=["check"],
        max_iterations=1,
    )

    assert report.status == "failed"
    assert report.failure_reason == "validation command failed: check (assertion_or_test_failure)"
    assert report.retry_decisions[0].decision == "stop"
