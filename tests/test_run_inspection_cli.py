from __future__ import annotations

import json
from pathlib import Path

from test_run_inspection import build_run, run_dir_of
from typer.testing import CliRunner

from rtl_agent.cli import app


def test_cli_inspect_valid_run(tmp_path: Path) -> None:
    build_run(tmp_path)
    output = tmp_path / "inspection.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["inspect-run", "--run-dir", str(run_dir_of(tmp_path)), "--output", str(output)],
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    summary = json.loads(result.stdout)
    assert summary["valid"] is True
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema_version"] == 1
    assert all(stage["validity"] == "valid" for stage in report["stages"])


def test_cli_inspect_invalid_run_exits_1_and_writes_report(tmp_path: Path) -> None:
    build_run(tmp_path)
    (run_dir_of(tmp_path) / "driver-trace.json").unlink()
    output = tmp_path / "inspection.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["inspect-run", "--run-dir", str(run_dir_of(tmp_path)), "--output", str(output)],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout)["valid"] is False
    # The report is still written despite the non-zero exit.
    assert output.exists()


def test_cli_inspect_missing_manifest_exits_2(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    runner = CliRunner()

    result = runner.invoke(app, ["inspect-run", "--run-dir", str(empty)])

    assert result.exit_code == 2
    assert "run manifest not found" in result.stderr
