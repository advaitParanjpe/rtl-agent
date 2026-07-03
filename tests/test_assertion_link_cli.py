from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from rtl_agent.cli import app

FIXTURE_TRIAGE = "examples/waveforms/triage-report.json"


def test_cli_link_assertion_waveform_writes_reports(tmp_path: Path) -> None:
    output = tmp_path / "link.json"
    slice_output = tmp_path / "slice.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "link-assertion-waveform",
            "--triage-report",
            FIXTURE_TRIAGE,
            "--assertion-id",
            "assertion-0",
            "--before",
            "15",
            "--after",
            "5",
            "--slice-output",
            str(slice_output),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    assert '"failure_timestamp_ticks": 40' in result.stdout
    link = json.loads(output.read_text(encoding="utf-8"))
    assert link["schema_version"] == 1
    assert link["selected_assertion"]["assertion_id"] == "assertion-0"
    slice_report = json.loads(slice_output.read_text(encoding="utf-8"))
    assert slice_report["window"]["failure_time"] == 40


def test_cli_rejects_when_no_assertion_selected(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "link-assertion-waveform",
            "--triage-report",
            FIXTURE_TRIAGE,
            "--slice-output",
            str(tmp_path / "slice.json"),
            "--output",
            str(tmp_path / "link.json"),
        ],
    )

    assert result.exit_code == 2
    assert "no assertion selected" in result.stderr
