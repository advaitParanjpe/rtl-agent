from __future__ import annotations

import json
from pathlib import Path

from test_review import make_review_inputs
from typer.testing import CliRunner

from rtl_agent.cli import app


def test_cli_review_task_writes_report(tmp_path: Path) -> None:
    task_contract_path, repository_map_path, implementation_report_path, _repo = make_review_inputs(
        tmp_path
    )
    output = tmp_path / "review-report.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "review-task",
            "--task-contract",
            str(task_contract_path),
            "--repository-map",
            str(repository_map_path),
            "--implementation-report",
            str(implementation_report_path),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert '"outcome": "acceptable"' in result.stdout
    assert json.loads(output.read_text(encoding="utf-8"))["outcome"] == "acceptable"


def test_cli_review_task_can_fail_on_unacceptable(tmp_path: Path) -> None:
    task_contract_path, repository_map_path, implementation_report_path, _repo = make_review_inputs(
        tmp_path, validation_assertion="'missing_signal' in Path('rtl/top.sv').read_text()"
    )
    output = tmp_path / "review-report.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "review-task",
            "--task-contract",
            str(task_contract_path),
            "--repository-map",
            str(repository_map_path),
            "--implementation-report",
            str(implementation_report_path),
            "--output",
            str(output),
            "--fail-on-unacceptable",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(output.read_text(encoding="utf-8"))["outcome"] == "unacceptable"
