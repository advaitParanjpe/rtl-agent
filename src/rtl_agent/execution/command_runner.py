from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from uuid import uuid4

from rtl_agent.artifacts import RunStore
from rtl_agent.config import AgentConfig
from rtl_agent.models import CommandResult, CommandStatus, utc_now


class CommandRunner:
    def __init__(
        self,
        config: AgentConfig,
        run_store: RunStore,
        command_id_factory: Callable[[str], str] | None = None,
    ) -> None:
        self.config = config
        self.run_store = run_store
        self.command_id_factory = command_id_factory

    def run_named(self, name: str) -> CommandResult:
        if name not in self.config.commands:
            raise KeyError(f"unknown command: {name}")

        command = self.config.commands[name]
        cwd = self.config.command_cwd(command)
        self.config.assert_working_path_allowed(cwd)
        if not cwd.exists() or not cwd.is_dir():
            raise ValueError(f"command cwd does not exist or is not a directory: {cwd}")

        command_id = (
            self.command_id_factory(name)
            if self.command_id_factory is not None
            else f"{name}-{uuid4().hex[:8]}"
        )
        command_dir = self.run_store.command_dir(command_id)
        stdout_path = command_dir / "stdout.log"
        stderr_path = command_dir / "stderr.log"
        started_at = utc_now()
        started = time.monotonic()
        timeout = command.timeout_seconds or self.config.execution.timeout_seconds
        status = CommandStatus.FAILED
        exit_code: int | None = None
        error: str | None = None

        with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
            try:
                completed = subprocess.run(
                    command.argv,
                    cwd=cwd,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    timeout=timeout,
                    check=False,
                    shell=False,
                    env=None,
                )
                exit_code = completed.returncode
                status = CommandStatus.PASSED if exit_code == 0 else CommandStatus.FAILED
            except subprocess.TimeoutExpired:
                status = CommandStatus.TIMEOUT
                exit_code = None
                error = f"command timed out after {timeout} seconds"
                stderr_file.write((error + "\n").encode("utf-8"))
            except FileNotFoundError as exc:
                status = CommandStatus.EXEC_ERROR
                exit_code = None
                error = f"executable not found: {command.argv[0]}"
                stderr_file.write((error + "\n").encode("utf-8"))
                if exc.filename:
                    stderr_file.write(f"missing: {exc.filename}\n".encode())
            except OSError as exc:
                status = CommandStatus.EXEC_ERROR
                exit_code = None
                error = f"execution failed: {exc}"
                stderr_file.write((error + "\n").encode("utf-8"))

        ended_at = utc_now()
        duration = time.monotonic() - started
        result = CommandResult(
            command_id=command_id,
            command_name=name,
            argv=command.argv,
            cwd=cwd,
            status=status,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration,
            exit_code=exit_code,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            error=error,
        )
        self.run_store.write_command_result(command_dir, result)
        return result
