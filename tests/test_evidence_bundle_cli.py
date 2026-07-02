from __future__ import annotations

import json
from pathlib import Path

from test_evidence_bundle import make_run
from typer.testing import CliRunner

from rtl_agent.cli import app


def test_cli_export_evidence_writes_bundle(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    output_dir = tmp_path / "bundle"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["export-evidence", "--run-dir", str(run_dir), "--output-dir", str(output_dir)],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert (output_dir / "manifest.json").exists()
    assert (output_dir / "bundle.json").exists()


def test_cli_export_evidence_can_fail_on_failed_export(tmp_path: Path) -> None:
    run_dir = tmp_path / ".rtl-agent" / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    output_dir = tmp_path / "bundle"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "export-evidence",
            "--run-dir",
            str(run_dir),
            "--output-dir",
            str(output_dir),
            "--fail-on-failed-export",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"] == "failed"
