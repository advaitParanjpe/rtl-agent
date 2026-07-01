from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class CommandStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    EXEC_ERROR = "exec_error"


class CommandResult(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = 1
    command_id: str
    command_name: str
    argv: list[str]
    cwd: Path
    status: CommandStatus
    started_at: datetime
    ended_at: datetime
    duration_seconds: float = Field(ge=0)
    exit_code: int | None
    stdout_path: Path
    stderr_path: Path
    error: str | None = None


class RunMetadata(BaseModel):
    schema_version: int = 1
    run_id: str
    created_at: datetime


class RunEvent(BaseModel):
    schema_version: int = 1
    timestamp: datetime
    event: str
    data: dict[str, Any] = Field(default_factory=dict)


class WorktreePlan(BaseModel):
    source_repo: Path
    worktree_path: Path
    git_add_command: list[str]
    git_remove_command: list[str]
