from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from rtl_agent.cli import app
from rtl_agent.models import CommandStatus
from rtl_agent.triage_models import TriageReport, TriageSource, WaveformReference

FIXTURE = Path("examples/waveforms/failure.vcd")


def test_cli_extract_waveform_window_writes_slice(tmp_path: Path) -> None:
    output = tmp_path / "slice.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "extract-waveform-window",
            "--vcd",
            str(FIXTURE),
            "--failure-time",
            "40",
            "--before",
            "15",
            "--after",
            "5",
            "--signal-prefix",
            "top.dut",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    assert '"selected_signals": 2' in result.stdout
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert {signal["name"] for signal in data["selected_signals"]} == {
        "top.dut.valid",
        "top.dut.state",
    }


def test_cli_requires_a_waveform_source(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "extract-waveform-window",
            "--failure-time",
            "10",
            "--output",
            str(tmp_path / "slice.json"),
        ],
    )

    assert result.exit_code == 2
    assert "either --vcd or --triage-report must be provided" in result.stderr


def test_cli_rejects_overwriting_the_source(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "extract-waveform-window",
            "--vcd",
            str(FIXTURE),
            "--failure-time",
            "40",
            "--output",
            str(FIXTURE),
        ],
    )

    assert result.exit_code == 2
    assert "overwrite the source waveform" in result.stderr


def test_cli_resolves_vcd_from_triage_report(tmp_path: Path) -> None:
    triage = TriageReport(
        command_name="sim",
        command_status=str(CommandStatus.FAILED),
        command_exit_code=1,
        command_result_path=tmp_path / "result.json",
        stdout_path=tmp_path / "stdout.log",
        stderr_path=tmp_path / "stderr.log",
        waveform_references=[
            WaveformReference(
                source=TriageSource.STDOUT,
                line=1,
                path="failure.vcd",
                exists=True,
                resolved_path=FIXTURE.resolve(),
                evidence="dumped failure.vcd",
            )
        ],
    )
    triage_path = tmp_path / "triage.json"
    triage_path.write_text(json.dumps(triage.model_dump(mode="json")), encoding="utf-8")
    output = tmp_path / "slice.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "extract-waveform-window",
            "--triage-report",
            str(triage_path),
            "--failure-time",
            "40",
            "--before",
            "15",
            "--after",
            "5",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["source"]["path"].endswith("failure.vcd")
    assert data["source"]["timescale"] == "1ns"
