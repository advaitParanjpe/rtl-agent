from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from rtl_agent.cli import app


def test_cli_inspect_config(tmp_path: Path) -> None:
    config = tmp_path / "rtl-agent.yaml"
    config.write_text(
        """
schema_version: 1
repository_path: .
run_artifact_dir: .rtl-agent/runs
allowed_working_paths: [.]
commands:
  smoke:
    argv: [python3, --version]
""",
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(app, ["inspect-config", "--config", str(config)])

    assert result.exit_code == 0
    assert '"commands": [' in result.stdout
    assert '"smoke"' in result.stdout


def test_cli_run_command(tmp_path: Path) -> None:
    config = tmp_path / "rtl-agent.yaml"
    config.write_text(
        """
schema_version: 1
repository_path: .
run_artifact_dir: .rtl-agent/runs
allowed_working_paths: [.]
commands:
  smoke:
    argv: [python3, -c, "print('ok')"]
""",
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(app, ["run-command", "--config", str(config), "--command", "smoke"])

    assert result.exit_code == 0
    assert '"status": "passed"' in result.stdout
    assert list((tmp_path / ".rtl-agent" / "runs").glob("*/commands/*/stdout.log"))
