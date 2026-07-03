from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from rtl_agent.cli import app


def make_inputs(tmp_path: Path) -> tuple[Path, Path]:
    runner = CliRunner()
    repo_map = tmp_path / "repo-map.json"
    result = runner.invoke(
        app,
        [
            "inspect-repo",
            "--repo",
            "examples/simple-rtl",
            "--config",
            "examples/simple-rtl-agent.yaml",
            "--output",
            str(repo_map),
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    sig_map = tmp_path / "sigmap.json"
    result = runner.invoke(
        app,
        [
            "map-signals",
            "--repository-map",
            str(repo_map),
            "--signal",
            "top.u_child.clk",
            "--output",
            str(sig_map),
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    return sig_map, repo_map


def test_cli_trace_drivers_writes_report(tmp_path: Path) -> None:
    sig_map, repo_map = make_inputs(tmp_path)
    output = tmp_path / "trace.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "trace-drivers",
            "--signal-source-map",
            str(sig_map),
            "--repository-map",
            str(repo_map),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema_version"] == 1
    traced = report["traced_signals"][0]
    assert traced["signal"] == "top.u_child.clk"
    port = next(d for d in traced["drivers"] if d["kind"] == "port_connection")
    assert port["label"] == "inferred_textual"


def test_cli_trace_drivers_rejects_missing_repository_map(tmp_path: Path) -> None:
    sig_map, _ = make_inputs(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "trace-drivers",
            "--signal-source-map",
            str(sig_map),
            "--repository-map",
            str(tmp_path / "missing.json"),
            "--output",
            str(tmp_path / "trace.json"),
        ],
    )

    assert result.exit_code == 2
    assert "could not load repository map" in result.stderr
