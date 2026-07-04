from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

FAILURE_INTELLIGENCE_RUN_SCHEMA_VERSION = 2


class RunStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class StageDisposition(StrEnum):
    EXECUTED = "executed"
    REUSED = "reused"
    REGENERATED = "regenerated"
    SKIPPED = "skipped"
    FAILED = "failed"


class RunStage(BaseModel):
    name: str
    disposition: StageDisposition
    reason: str | None = None
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
    sha256: str | None = None


class FailureIntelligenceRunManifest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = FAILURE_INTELLIGENCE_RUN_SCHEMA_VERSION
    run_id: str
    run_dir: Path
    created_at: datetime
    status: RunStatus
    resumed: bool = False
    replay_from: str | None = None
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
