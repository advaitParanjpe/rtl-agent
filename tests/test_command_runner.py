from __future__ import annotations

from pathlib import Path

from rtl_agent.artifacts import RunStore
from rtl_agent.config import AgentConfig, CommandConfig
from rtl_agent.execution import CommandRunner


def make_config(tmp_path: Path, command: CommandConfig) -> AgentConfig:
    return AgentConfig(
        repository_path=tmp_path,
        run_artifact_dir=tmp_path / ".rtl-agent" / "runs",
        allowed_working_paths=[tmp_path],
        protected_paths=[tmp_path / ".git"],
        commands={"cmd": command},
    )


def test_command_runner_writes_output_to_artifacts(tmp_path: Path) -> None:
    config = make_config(
        tmp_path,
        CommandConfig(argv=["python3", "-c", "print('hello')"], cwd=tmp_path),
    )
    store = RunStore(config.run_root, run_id="run-1")
    store.create()

    result = CommandRunner(config, store).run_named("cmd")

    assert result.exit_code == 0
    assert result.status == "passed"
    assert result.stdout_path.read_text(encoding="utf-8") == "hello\n"
    assert (store.run_dir / "commands" / result.command_id / "result.json").exists()


def test_command_runner_handles_missing_executable(tmp_path: Path) -> None:
    config = make_config(
        tmp_path,
        CommandConfig(argv=["definitely-not-a-real-rtl-agent-command"], cwd=tmp_path),
    )
    store = RunStore(config.run_root, run_id="run-1")
    store.create()

    result = CommandRunner(config, store).run_named("cmd")

    assert result.exit_code is None
    assert result.status == "exec_error"
    assert "executable not found" in result.stderr_path.read_text(encoding="utf-8")


def test_command_runner_handles_timeout(tmp_path: Path) -> None:
    config = make_config(
        tmp_path,
        CommandConfig(
            argv=["python3", "-c", "import time; time.sleep(5)"], cwd=tmp_path, timeout_seconds=1
        ),
    )
    store = RunStore(config.run_root, run_id="run-1")
    store.create()

    result = CommandRunner(config, store).run_named("cmd")

    assert result.exit_code is None
    assert result.status == "timeout"
    assert "timed out" in result.stderr_path.read_text(encoding="utf-8")
