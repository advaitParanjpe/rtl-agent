from __future__ import annotations

import json
from pathlib import Path

from test_failure_report import make_graph, make_reduction
from typer.testing import CliRunner

from rtl_agent.cli import app


def test_cli_synthesize_writes_json_and_markdown(tmp_path: Path) -> None:
    graph = make_graph(
        tmp_path,
        roots=[("state", "top.dut.state", 25), ("valid", "top.dut.valid", 25)],
        earliest=25,
    )
    reduction = make_reduction(tmp_path)
    output = tmp_path / "failure-report.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "synthesize-failure-report",
            "--divergence-graph",
            str(graph),
            "--reduction",
            str(reduction),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema_version"] == 1
    assert len(report["observed_failure_facts"]) == 2
    markdown = (tmp_path / "failure-report.md").read_text(encoding="utf-8")
    assert "# Failure Report" in markdown
    assert "never identifies a root cause" in markdown


def test_cli_rejects_missing_divergence_graph(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "synthesize-failure-report",
            "--divergence-graph",
            str(tmp_path / "missing.json"),
            "--output",
            str(tmp_path / "out.json"),
        ],
    )

    assert result.exit_code == 2
    assert "could not load failure-divergence-graph" in result.stderr
