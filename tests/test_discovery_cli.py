from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from rtl_agent.cli import app


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "rtl"
    write(repo / "top.sv", "module top; endmodule\n")
    write(repo / "Makefile", "lint:\n\tverilator --lint-only top.sv\n")
    return repo


def test_cli_inspect_repo_success(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    output = tmp_path / "map.json"
    runner = CliRunner()

    result = runner.invoke(app, ["inspect-repo", "--repo", str(repo), "--output", str(output)])

    assert result.exit_code == 0
    assert '"files_indexed": 2' in result.stdout
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["files"][0]["path"] == "Makefile"


def test_cli_inspect_repo_failure(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["inspect-repo", "--repo", str(tmp_path / "missing"), "--output", str(tmp_path / "m.json")],
    )

    assert result.exit_code == 2
    assert "repository path is not a directory" in result.stderr


def test_cli_discover_writes_run_artifact(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    config = tmp_path / "rtl-agent.yaml"
    config.write_text(
        f"""
schema_version: 1
repository_path: {repo}
run_artifact_dir: {tmp_path / ".rtl-agent" / "runs"}
allowed_working_paths:
  - {repo}
discovery:
  max_file_count: 100
commands: {{}}
""",
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(app, ["discover", "--config", str(config)])

    assert result.exit_code == 0
    assert list((tmp_path / ".rtl-agent" / "runs").glob("*/discovery/repository-map.json"))
