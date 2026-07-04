from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

RUN_INSPECTION_SCHEMA_VERSION = 1


class ArtifactValidity(StrEnum):
    VALID = "valid"
    MISSING = "missing"
    HASH_MISMATCH = "hash_mismatch"
    SCHEMA_MALFORMED = "schema_malformed"
    SCHEMA_UNSUPPORTED = "schema_unsupported"
    UNSAFE_PATH = "unsafe_path"


class StageValidity(StrEnum):
    VALID = "valid"
    INCOMPLETE = "incomplete"
    STALE = "stale"
    INVALID = "invalid"


class ArtifactInspection(BaseModel):
    artifact_id: str
    kind: str
    relative_path: str
    validity: ArtifactValidity
    detail: str | None = None
    recorded_sha256: str | None = None
    actual_sha256: str | None = None
    recorded_schema_version: int | None = None
    actual_schema_version: int | None = None


class StageInspection(BaseModel):
    name: str
    disposition: str
    validity: StageValidity
    outputs: list[str] = Field(default_factory=list)
    detail: str | None = None


class ExternalInputInspection(BaseModel):
    name: str
    path: str
    recorded_exists: bool
    exists_now: bool


class RunInspectionReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = RUN_INSPECTION_SCHEMA_VERSION
    run_dir: Path
    manifest_run_id: str | None = None
    manifest_schema_version: int | None = None
    manifest_status: str | None = None
    valid: bool
    external_inputs_present: bool
    artifacts: list[ArtifactInspection] = Field(default_factory=list)
    stages: list[StageInspection] = Field(default_factory=list)
    external_inputs: list[ExternalInputInspection] = Field(default_factory=list)
    valid_artifacts: int = Field(default=0, ge=0)
    missing_artifacts: int = Field(default=0, ge=0)
    invalid_artifacts: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)
    parser_notes: list[str] = Field(default_factory=list)
