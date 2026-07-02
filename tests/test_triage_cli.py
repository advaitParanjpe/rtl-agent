from __future__ import annotations

import json
from pathlib import Path

from test_triage import write_command_result
from typer.testing import CliRunner

from rtl_agent.cli import app


def test_cli_triage_command_writes_report(tmp_path: Path) -> None:
    result_path = write_command_result(
        tmp_path,
        stderr="ASSERTION FAILED property p_ready at time 42 ns; waveform dump.fst\n",
    )
    output = tmp_path / "triage.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["triage-command", "--command-result", str(result_path), "--output", str(output)],
    )

    assert result.exit_code == 0
    assert '"assertion_failures": 1' in result.stdout
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["waveform_references"][0]["path"] == "dump.fst"


def test_cli_triage_command_rejects_missing_result(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "triage-command",
            "--command-result",
            str(tmp_path / "missing.json"),
            "--output",
            str(tmp_path / "triage.json"),
        ],
    )

    assert result.exit_code == 2
    assert "could not load command result" in result.stderr
