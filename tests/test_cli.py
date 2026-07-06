from __future__ import annotations

import re
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


def test_readme_documented_commands_have_help() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    documented = {
        match.group(1)
        for match in re.finditer(r"^rtl-agent ([a-z][a-z-]+)\b", readme, re.MULTILINE)
    }
    expected = {
        "assess-verification",
        "cluster-failures",
        "compare-waveforms",
        "compare-fingerprints",
        "discover",
        "divergence-graph",
        "export-evidence",
        "export-failure-package",
        "fingerprint-run",
        "extract-waveform-window",
        "implement-task",
        "inspect-config",
        "inspect-repo",
        "inspect-run",
        "link-assertion-waveform",
        "map-signals",
        "minimize-stimulus",
        "parse-issue",
        "reduce-signals",
        "review-task",
        "run-benchmark",
        "run-command",
        "run-counterfactual",
        "run-failure-intelligence",
        "synthesize-failure-report",
        "trace-drivers",
        "triage-command",
    }
    runner = CliRunner()

    assert documented == expected
    for command in sorted(documented):
        result = runner.invoke(app, [command, "--help"])
        assert result.exit_code == 0, command
