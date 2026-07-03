from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

EVIDENCE_BUNDLE_MANIFEST_SCHEMA_VERSION = 1
EVIDENCE_BUNDLE_REPORT_SCHEMA_VERSION = 1


class EvidenceBundleStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


class EvidenceArtifactKind(StrEnum):
    RUN_METADATA = "run_metadata"
    RUN_EVENTS = "run_events"
    COMMAND_RESULT = "command_result"
    COMMAND_STDOUT = "command_stdout"
    COMMAND_STDERR = "command_stderr"
    DISCOVERY_REPOSITORY_MAP = "discovery_repository_map"
    IMPLEMENTATION_REPORT = "implementation_report"
    REVIEW_REPORT = "review_report"
    TRIAGE_REPORT = "triage_report"
    VERIFICATION_STRENGTH_REPORT = "verification_strength_report"
    BENCHMARK_REPORT = "benchmark_report"
    WAVEFORM_SLICE_REPORT = "waveform_slice_report"
    ASSERTION_WAVEFORM_LINK_REPORT = "assertion_waveform_link_report"
    OTHER_JSON = "other_json"
    OTHER_ARTIFACT = "other_artifact"


class EvidenceBundleManifest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = EVIDENCE_BUNDLE_MANIFEST_SCHEMA_VERSION
    run_dir: Path
    output_dir: Path
    include_contents: bool = False
    referenced_only_patterns: list[str] = Field(
        default_factory=lambda: ["*.log", "*.vcd", "*.fst", "*.fsdb", "*.wlf", "*.ghw"]
    )
    optional_artifact_paths: list[str] = Field(
        default_factory=lambda: [
            "events.jsonl",
            "discovery/repository-map.json",
            "implementation/report.json",
            "benchmarks/report.json",
        ]
    )

    @model_validator(mode="after")
    def validate_schema_version(self) -> EvidenceBundleManifest:
        if self.schema_version != EVIDENCE_BUNDLE_MANIFEST_SCHEMA_VERSION:
            raise ValueError("only evidence bundle manifest schema_version 1 is supported")
        if self.include_contents:
            raise ValueError("evidence bundle export is index-only and cannot include contents")
        return self


class EvidenceArtifactReference(BaseModel):
    artifact_id: str
    kind: EvidenceArtifactKind
    source_path: Path
    relative_path: str
    exists: bool
    size_bytes: int | None = None
    sha256: str | None = None
    schema_version: int | None = None
    included_in_bundle: bool = False
    omitted_reason: str | None = None
    provenance: str


class EvidenceBundleReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = EVIDENCE_BUNDLE_REPORT_SCHEMA_VERSION
    status: EvidenceBundleStatus
    run_dir: Path
    output_dir: Path
    manifest_path: Path
    artifacts: list[EvidenceArtifactReference] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    failure_reason: str | None = None
    summary: str
