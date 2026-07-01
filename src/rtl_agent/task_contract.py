from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

TASK_CONTRACT_SCHEMA_VERSION = 1


class RequirementSource(StrEnum):
    HEADING = "heading"
    CHECKLIST = "checklist"
    FENCED_BLOCK = "fenced_block"
    INLINE = "inline"


class IssueReference(BaseModel):
    value: str
    kind: str
    line: int
    in_repository_map: bool | None = None


class ParsedRequirement(BaseModel):
    text: str
    line: int
    source: RequirementSource


class ValidationCommand(BaseModel):
    command: list[str]
    raw: str
    line: int
    source: RequirementSource


class IssueChecklistItem(BaseModel):
    text: str
    checked: bool
    line: int


class RepositoryMapContext(BaseModel):
    path: Path
    schema_version: int
    repository_root: Path
    file_count: int
    command_count: int
    matched_paths: list[str] = Field(default_factory=list)
    unmatched_paths: list[str] = Field(default_factory=list)


class TaskContract(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = TASK_CONTRACT_SCHEMA_VERSION
    tool_version: str
    issue_path: Path
    repository_map: RepositoryMapContext | None = None
    title: str | None = None
    requested_behavior: list[ParsedRequirement] = Field(default_factory=list)
    scoped_repository_context: list[IssueReference] = Field(default_factory=list)
    invariants: list[ParsedRequirement] = Field(default_factory=list)
    acceptance_criteria: list[ParsedRequirement] = Field(default_factory=list)
    validation_commands: list[ValidationCommand] = Field(default_factory=list)
    prohibited_shortcuts: list[ParsedRequirement] = Field(default_factory=list)
    evidence_requirements: list[ParsedRequirement] = Field(default_factory=list)
    checklist: list[IssueChecklistItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    parser_notes: list[str] = Field(default_factory=list)
