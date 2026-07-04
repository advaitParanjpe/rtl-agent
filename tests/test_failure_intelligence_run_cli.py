from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from rtl_agent.cli import app

FAILING_VCD = "examples/waveforms/failure.vcd"
PASSING_VCD = "examples/waveforms/passing.vcd"
SIMPLE_RTL = "examples/simple-rtl"


def test_cli_run_writes_run_directory(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run-failure-intelligence",
            "--failing-vcd",
            FAILING_VCD,
            "--passing-vcd",
            PASSING_VCD,
            "--repo",
            SIMPLE_RTL,
            "--failure-time",
            "40",
            "--before",
            "15",
            "--after",
            "15",
            "--run-root",
            str(tmp_path / "runs"),
            "--run-id",
            "cli-run",
        ],
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    summary = json.loads(result.stdout)
    assert summary["status"] == "completed"
    assert summary["run_id"] == "cli-run"
    run_dir = tmp_path / "runs" / "cli-run"
    assert (run_dir / "failure-report.json").exists()
    assert (run_dir / "failure-report.md").exists()
    assert (run_dir / "run-manifest.json").exists()


def test_cli_run_reports_stage_failure_with_exit_1(tmp_path: Path) -> None:
    bad = tmp_path / "bad.vcd"
    bad.write_text("not a vcd", encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run-failure-intelligence",
            "--failing-vcd",
            FAILING_VCD,
            "--passing-vcd",
            str(bad),
            "--repo",
            SIMPLE_RTL,
            "--failure-time",
            "40",
            "--before",
            "15",
            "--after",
            "15",
            "--run-root",
            str(tmp_path / "runs"),
            "--run-id",
            "cli-fail",
        ],
    )

    assert result.exit_code == 1
    summary = json.loads(result.stdout)
    assert summary["status"] == "failed"
    assert "extract-passing" in summary["failure_reason"]
    # A manifest is still written for the partial run.
    assert (tmp_path / "runs" / "cli-fail" / "run-manifest.json").exists()
