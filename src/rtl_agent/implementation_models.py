from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

IMPLEMENTATION_REPORT_SCHEMA_VERSION = 1


class ProviderRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ToolName(StrEnum):
    READ_FILE = "read_file"
    REPLACE_TEXT = "replace_text"


class ImplementationStatus(StrEnum):
    PROPOSED_DIFF = "proposed_diff"
    FAILED = "failed"


class VerificationFailureCategory(StrEnum):
    PASSED = "passed"
    TIMEOUT = "timeout"
    MISSING_EXECUTABLE = "missing_executable"
    ASSERTION_TEST_FAILURE = "assertion_or_test_failure"
    LINT_SYNTAX_FAILURE = "lint_or_syntax_failure"
    COMMAND_FAILURE = "command_failure"
    UNKNOWN_FAILURE = "unknown_failure"


class RetryDecision(BaseModel):
    iteration: int
    command_name: str
    decision: str
    reason: str


class VerificationClassification(BaseModel):
    category: VerificationFailureCategory
    summary: str
    evidence: list[str] = Field(default_factory=list)
    stdout_excerpt: list[str] = Field(default_factory=list)
    stderr_excerpt: list[str] = Field(default_factory=list)


class ProviderMessage(BaseModel):
    role: ProviderRole
    content: str


class ProviderRequest(BaseModel):
    task_contract_title: str | None = None
    allowed_files: list[str]
    allowed_validation_commands: list[str]
    iteration: int
    messages: list[ProviderMessage]
    failure_evidence: list[VerificationClassification] = Field(default_factory=list)


class ToolCall(BaseModel):
    tool: ToolName
    path: str
    old: str | None = None
    new: str | None = None


class ProviderResponse(BaseModel):
    message: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    validation_commands: list[str] = Field(default_factory=list)
    stop: bool = False


class ToolResult(BaseModel):
    tool: ToolName
    path: str
    status: str
    message: str


class ValidationResultSummary(BaseModel):
    command_name: str
    status: str
    exit_code: int | None
    result_path: Path
    stdout_path: Path
    stderr_path: Path
    classification: VerificationClassification


class ImplementationReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = IMPLEMENTATION_REPORT_SCHEMA_VERSION
    status: ImplementationStatus
    task_contract_path: Path
    repository_map_path: Path
    repository_root: Path
    provider: str
    iterations: int
    allowed_files: list[str]
    allowed_validation_commands: list[str]
    applied_files: list[str] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    validation_results: list[ValidationResultSummary] = Field(default_factory=list)
    retry_decisions: list[RetryDecision] = Field(default_factory=list)
    diff_path: Path | None = None
    failure_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
