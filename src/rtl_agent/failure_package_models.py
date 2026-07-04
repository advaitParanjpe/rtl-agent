from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

FAILURE_PACKAGE_SCHEMA_VERSION = 1


class PackageStatus(StrEnum):
    VALID = "valid"
    FAILED = "failed"


class PackageFileRole(StrEnum):
    RUN_MANIFEST = "run_manifest"
    INSPECTION_REPORT = "inspection_report"
    FAILURE_REPORT = "failure_report"
    FAILURE_REPORT_MARKDOWN = "failure_report_markdown"
    EVIDENCE_ARTIFACT = "evidence_artifact"


class PackagedFile(BaseModel):
    package_path: str
    role: PackageFileRole
    kind: str | None = None
    size_bytes: int = Field(ge=0)
    sha256: str
    schema_version: int | None = None
    run_relative_path: str | None = None


class FailurePackageManifest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = FAILURE_PACKAGE_SCHEMA_VERSION
    package_status: PackageStatus
    run_id: str | None = None
    run_manifest_schema_version: int | None = None
    source_run_dir: str
    verified: bool = False
    file_count: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    files: list[PackagedFile] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    parser_notes: list[str] = Field(default_factory=list)
