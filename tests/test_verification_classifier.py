from __future__ import annotations

from pathlib import Path

from rtl_agent.models import CommandResult, CommandStatus, utc_now
from rtl_agent.verification import classify_command_result


def make_result(
    tmp_path: Path,
    status: CommandStatus,
    exit_code: int | None,
    stdout: str = "",
    stderr: str = "",
    error: str | None = None,
) -> CommandResult:
    stdout_path = tmp_path / "stdout.log"
    stderr_path = tmp_path / "stderr.log"
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    now = utc_now()
    return CommandResult(
        command_id="cmd-1",
        command_name="check",
        argv=["python3", "-c", "pass"],
        cwd=tmp_path,
        status=status,
        started_at=now,
        ended_at=now,
        duration_seconds=0,
        exit_code=exit_code,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        error=error,
    )


def test_classifies_timeout(tmp_path: Path) -> None:
    result = make_result(
        tmp_path, CommandStatus.TIMEOUT, None, stderr="command timed out", error="timed out"
    )

    classification = classify_command_result(result)

    assert classification.category == "timeout"


def test_classifies_missing_executable(tmp_path: Path) -> None:
    result = make_result(
        tmp_path,
        CommandStatus.EXEC_ERROR,
        None,
        stderr="executable not found",
        error="executable not found: nope",
    )

    classification = classify_command_result(result)

    assert classification.category == "missing_executable"


def test_classifies_lint_or_syntax_failure(tmp_path: Path) -> None:
    result = make_result(tmp_path, CommandStatus.FAILED, 1, stderr="%Error: syntax error")

    classification = classify_command_result(result)

    assert classification.category == "lint_or_syntax_failure"


def test_classifies_generic_command_failure_and_limits_excerpts(tmp_path: Path) -> None:
    result = make_result(
        tmp_path,
        CommandStatus.FAILED,
        2,
        stdout="\n".join(f"line {i}" for i in range(20)),
    )

    classification = classify_command_result(result)

    assert classification.category == "command_failure"
    assert len(classification.stdout_excerpt) == 8
