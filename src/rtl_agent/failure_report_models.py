from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

FAILURE_REPORT_SCHEMA_VERSION = 1


class ArtifactReference(BaseModel):
    """Provenance for an artifact that contributed to (or is cited by) the report."""

    artifact_id: str
    kind: str
    path: Path
    schema_version: int | None = None
    sha256: str | None = None


class DivergingSignalFact(BaseModel):
    signal: str | None = None
    identifier: str
    first_divergence_time: int | None = None
    failing_value: str | None = None
    passing_value: str | None = None
    xz_difference: bool = False
    divergence_score: int = Field(ge=0)
    source: str


class RankedRelevantSignal(BaseModel):
    name: str
    score: int = Field(ge=0)
    criteria: list[str] = Field(default_factory=list)
    source: str


class SourceLocation(BaseModel):
    identifier: str
    declaration_name: str
    declaration_kind: str
    file_path: str
    line: int
    mapping_status: str | None = None
    source: str


class DriverEvidence(BaseModel):
    source_signal: str
    depends_on: str
    label: str
    statement_kind: str
    evidence_file: str
    evidence_line: int
    statement_text: str | None = None
    guard: str | None = None
    source: str


class EvidenceGap(BaseModel):
    identifier: str
    kind: str
    detail: str
    source: str


class VerificationStatus(BaseModel):
    strength: str
    score: int = Field(ge=0, le=100)
    weak_patterns: list[str] = Field(default_factory=list)
    source: str


class ReviewStatus(BaseModel):
    outcome: str
    error_finding_ids: list[str] = Field(default_factory=list)
    source: str


class FailureReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = FAILURE_REPORT_SCHEMA_VERSION
    divergence_graph_path: Path
    observed_failure_facts: list[DivergingSignalFact] = Field(default_factory=list)
    earliest_divergence_time: int | None = None
    earliest_divergence_signals: list[str] = Field(default_factory=list)
    ranked_relevant_signals: list[RankedRelevantSignal] = Field(default_factory=list)
    candidate_source_locations: list[SourceLocation] = Field(default_factory=list)
    driver_dependency_evidence: list[DriverEvidence] = Field(default_factory=list)
    unresolved_evidence: list[EvidenceGap] = Field(default_factory=list)
    ambiguous_evidence: list[EvidenceGap] = Field(default_factory=list)
    verification_status: VerificationStatus | None = None
    review_status: ReviewStatus | None = None
    generated_from: list[ArtifactReference] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    parser_notes: list[str] = Field(default_factory=list)
