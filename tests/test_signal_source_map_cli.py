from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from rtl_agent.cli import app


def make_repo_map(tmp_path: Path) -> Path:
    runner = CliRunner()
    out = tmp_path / "repo-map.json"
    result = runner.invoke(
        app,
        [
            "inspect-repo",
            "--repo",
            "examples/simple-rtl",
            "--config",
            "examples/simple-rtl-agent.yaml",
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    return out


def test_cli_map_signals_writes_report(tmp_path: Path) -> None:
    repo = make_repo_map(tmp_path)
    output = tmp_path / "signal-source-map.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "map-signals",
            "--repository-map",
            str(repo),
            "--signal",
            "top.u_child.clk",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema_version"] == 1
    mapping = report["mappings"][0]
    assert mapping["signal"] == "top.u_child.clk"
    assert mapping["status"] == "exact"
    assert mapping["candidates"][0]["file_path"] == "rtl/top.sv"


def test_cli_map_signals_rejects_missing_repository_map(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "map-signals",
            "--repository-map",
            str(tmp_path / "missing.json"),
            "--signal",
            "top.a",
            "--output",
            str(tmp_path / "out.json"),
        ],
    )

    assert result.exit_code == 2
    assert "could not load repository map" in result.stderr
