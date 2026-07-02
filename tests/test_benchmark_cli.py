from __future__ import annotations

import json
from pathlib import Path

from test_benchmark import make_config, make_manifest
from typer.testing import CliRunner

from rtl_agent.cli import app


def test_cli_run_benchmark_writes_report(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    manifest = make_manifest(tmp_path, config)
    runner = CliRunner()

    result = runner.invoke(app, ["run-benchmark", "--manifest", str(manifest)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert Path(payload["output"]).exists()


def test_cli_run_benchmark_can_fail_on_unmet_expected(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    manifest = make_manifest(tmp_path, config, command="fail", expected_status="passed")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run-benchmark",
            "--manifest",
            str(manifest),
            "--fail-on-unmet-expected",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"] == "failed"
