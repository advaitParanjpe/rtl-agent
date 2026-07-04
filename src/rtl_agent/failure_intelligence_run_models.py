from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

FAILURE_INTELLIGENCE_RUN_SCHEMA_VERSION = 1


class RunStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class StageStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RunStage(BaseModel):
    name: str
    status: StageStatus
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    duration_seconds: float = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    failure_reason: str | None = None


class RunArtifact(BaseModel):
    artifact_id: str
    kind: str
    relative_path: str
    schema_version: int | None = None


class FailureIntelligenceRunManifest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = FAILURE_INTELLIGENCE_RUN_SCHEMA_VERSION
    run_id: str
    run_dir: Path
    created_at: datetime
    status: RunStatus
    failing_vcd: Path
    passing_vcd: Path
    repository_root: Path
    failure_time: int = Field(ge=0)
    before: int = Field(ge=0)
    after: int = Field(ge=0)
    stages: list[RunStage] = Field(default_factory=list)
    artifacts: list[RunArtifact] = Field(default_factory=list)
    failure_report_path: str | None = None
    failure_report_markdown_path: str | None = None
    failure_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
    parser_notes: list[str] = Field(default_factory=list)
