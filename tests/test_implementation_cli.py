from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from rtl_agent.cli import app
from rtl_agent.discovery import discover_repository, write_repository_map
from rtl_agent.issues import parse_issue_file, write_task_contract


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_cli_implement_task_writes_report(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write(repo / "rtl" / "top.sv", "module top;\n  wire old_signal;\nendmodule\n")
    config = tmp_path / "rtl-agent.yaml"
    config.write_text(
        f"""
schema_version: 1
repository_path: {repo}
run_artifact_dir: {tmp_path / ".rtl-agent" / "runs"}
allowed_working_paths:
  - {repo}
commands:
  check:
    argv:
      - python3
      - -c
      - "from pathlib import Path; assert 'new_signal' in Path('rtl/top.sv').read_text()"
    cwd: {repo}
""",
        encoding="utf-8",
    )
    repository_map = discover_repository(repo)
    repository_map_path = tmp_path / "repository-map.json"
    write_repository_map(repository_map, repository_map_path)
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

## Evidence Requirements
- Report validation results.
""",
    )
    task_contract = parse_issue_file(issue, repository_map_path)
    task_contract_path = tmp_path / "task-contract.json"
    write_task_contract(task_contract, task_contract_path)
    provider_plan = tmp_path / "plan.json"
    provider_plan.write_text(
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
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "implement-task",
            "--config",
            str(config),
            "--task-contract",
            str(task_contract_path),
            "--repository-map",
            str(repository_map_path),
            "--provider-plan",
            str(provider_plan),
            "--allowed-file",
            "rtl/top.sv",
            "--validation-command",
            "check",
            "--max-iterations",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert '"status": "proposed_diff"' in result.stdout
    assert list((tmp_path / ".rtl-agent" / "runs").glob("*/implementation/report.json"))
