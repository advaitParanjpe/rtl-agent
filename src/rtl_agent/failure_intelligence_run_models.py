from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

FAILURE_INTELLIGENCE_RUN_SCHEMA_VERSION = 3


class RunStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class StageDisposition(StrEnum):
    EXECUTED = "executed"
    REUSED = "reused"
    REGENERATED = "regenerated"
    SKIPPED = "skipped"
    FAILED = "failed"


class PathKind(StrEnum):
    RUN_RELATIVE = "run_relative"
    EXTERNAL = "external"


class PathRef(BaseModel):
    """A path recorded with its provenance kind.

    ``run_relative`` paths are POSIX paths under the run directory and are
    resolved against the current run directory (making the run portable).
    ``external`` paths live outside the run directory and are recorded as
    absolute paths that must be supplied again explicitly.
    """

    kind: PathKind
    path: str


class ExternalInput(BaseModel):
    name: str
    path: str
    exists: bool


class RunStage(BaseModel):
    name: str
    disposition: StageDisposition
    reason: str | None = None
    inputs: list[PathRef] = Field(default_factory=list)
    outputs: list[PathRef] = Field(default_factory=list)
    duration_seconds: float = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    failure_reason: str | None = None


class RunArtifact(BaseModel):
    artifact_id: str
    kind: str
    path_kind: PathKind = PathKind.RUN_RELATIVE
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
    external_inputs: list[ExternalInput] = Field(default_factory=list)
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
