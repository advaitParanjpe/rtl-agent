from __future__ import annotations

import json
from pathlib import Path

from test_failure_divergence_graph import standard_inputs
from typer.testing import CliRunner

from rtl_agent.cli import app


def test_cli_divergence_graph_writes_report(tmp_path: Path) -> None:
    comparison, sig_map, trace = standard_inputs(tmp_path)
    output = tmp_path / "graph.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "divergence-graph",
            "--comparison",
            str(comparison),
            "--signal-source-map",
            str(sig_map),
            "--driver-trace",
            str(trace),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema_version"] == 1
    assert report["root_identifiers"] == ["valid"]
    root = next(n for n in report["nodes"] if n["identifier"] == "valid")
    assert root["divergence"]["first_divergence_time"] == 30


def test_cli_divergence_graph_rejects_missing_input(tmp_path: Path) -> None:
    comparison, sig_map, _ = standard_inputs(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "divergence-graph",
            "--comparison",
            str(comparison),
            "--signal-source-map",
            str(sig_map),
            "--driver-trace",
            str(tmp_path / "missing.json"),
            "--output",
            str(tmp_path / "graph.json"),
        ],
    )

    assert result.exit_code == 2
    assert "could not load driver-trace report" in result.stderr
