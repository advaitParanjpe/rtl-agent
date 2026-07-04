from __future__ import annotations

import json
from pathlib import Path

from test_run_inspection import build_run, edit_manifest, run_dir_of
from typer.testing import CliRunner

from rtl_agent.cli import app


def test_cli_export_valid_run(tmp_path: Path) -> None:
    build_run(tmp_path)
    package = tmp_path / "pkg"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "export-failure-package",
            "--run-dir",
            str(run_dir_of(tmp_path)),
            "--output",
            str(package),
        ],
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    summary = json.loads(result.stdout)
    assert summary["package_status"] == "valid"
    assert summary["verified"] is True
    assert (package / "package-manifest.json").exists()


def test_cli_export_invalid_run_exits_2(tmp_path: Path) -> None:
    build_run(tmp_path)
    (run_dir_of(tmp_path) / "driver-trace.json").unlink()
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "export-failure-package",
            "--run-dir",
            str(run_dir_of(tmp_path)),
            "--output",
            str(tmp_path / "pkg"),
        ],
    )

    assert result.exit_code == 2
    assert "refusing to export" in result.stderr


def test_cli_export_allow_failed(tmp_path: Path) -> None:
    build_run(tmp_path)
    edit_manifest(run_dir_of(tmp_path), lambda raw: raw.__setitem__("status", "failed"))
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "export-failure-package",
            "--run-dir",
            str(run_dir_of(tmp_path)),
            "--output",
            str(tmp_path / "pkg"),
            "--allow-failed",
        ],
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["package_status"] == "failed"
