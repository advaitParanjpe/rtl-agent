from __future__ import annotations

from pathlib import Path

import pytest

from rtl_agent.config import load_config


def test_load_config_resolves_relative_paths(tmp_path: Path) -> None:
    config_path = tmp_path / "rtl-agent.yaml"
    config_path.write_text(
        """
schema_version: 1
repository_path: repo
run_artifact_dir: .rtl-agent/runs
allowed_working_paths: [repo]
protected_paths: [repo/.git]
commands:
  smoke:
    argv: [python3, --version]
    cwd: repo
""",
        encoding="utf-8",
    )
    (tmp_path / "repo").mkdir()

    config = load_config(config_path)

    assert config.repository_root == (tmp_path / "repo").resolve()
    assert config.run_root == (tmp_path / ".rtl-agent" / "runs").resolve()
    assert "smoke" in config.commands


def test_rejects_disallowed_working_path(tmp_path: Path) -> None:
    config_path = tmp_path / "rtl-agent.yaml"
    config_path.write_text(
        """
schema_version: 1
repository_path: .
run_artifact_dir: .rtl-agent/runs
allowed_working_paths: [allowed]
commands: {}
""",
        encoding="utf-8",
    )
    config = load_config(config_path)

    with pytest.raises(ValueError, match="outside allowed"):
        config.assert_working_path_allowed(tmp_path / "elsewhere")
