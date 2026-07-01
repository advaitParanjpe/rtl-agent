from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from rtl_agent.cli import app


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_cli_parse_issue_success(tmp_path: Path) -> None:
    issue = tmp_path / "issue.md"
    output = tmp_path / "task-contract.json"
    write(
        issue,
        """# Add reset test

## Requested Behavior
- Add an explicit reset test for `tb/top_tb.sv`.

## Acceptance Criteria
- Reset behavior is covered.

## Validation
```bash
python3 scripts/check.py
```

## Evidence
- Report validation results.
""",
    )
    runner = CliRunner()

    result = runner.invoke(app, ["parse-issue", "--issue", str(issue), "--output", str(output)])

    assert result.exit_code == 0
    assert '"validation_commands": 1' in result.stdout
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["title"] == "Add reset test"


def test_cli_parse_issue_invalid_issue_path(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "parse-issue",
            "--issue",
            str(tmp_path / "missing.md"),
            "--output",
            str(tmp_path / "x.json"),
        ],
    )

    assert result.exit_code == 2
    assert "issue path is not a file" in result.stderr


def test_cli_parse_issue_malformed_repository_map(tmp_path: Path) -> None:
    issue = tmp_path / "issue.md"
    output = tmp_path / "task-contract.json"
    bad_map = tmp_path / "bad-map.json"
    write(issue, "# Issue\n")
    write(bad_map, "{}")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "parse-issue",
            "--issue",
            str(issue),
            "--repository-map",
            str(bad_map),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 2
    assert "malformed repository map" in result.stderr
