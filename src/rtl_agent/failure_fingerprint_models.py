from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

FAILURE_FINGERPRINT_SCHEMA_VERSION = 1
FINGERPRINT_COMPARISON_SCHEMA_VERSION = 1


class FingerprintMatchKind(StrEnum):
    EXACT = "exact"
    SAME_FAMILY = "same_likely_observed_failure_family"
    RELATED_DIFFERENT = "related_but_materially_different_failure"
    INSUFFICIENT = "insufficient_evidence_to_compare"


class FingerprintArtifactInput(BaseModel):
    kind: str
    path: Path
    schema_version: int | None = None


class FingerprintComponent(BaseModel):
    name: str
    values: list[str] = Field(default_factory=list)


class FingerprintDigest(BaseModel):
    exact: str
    family: str
    canonical: str | None = None


class FailureFingerprintReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = FAILURE_FINGERPRINT_SCHEMA_VERSION
    source_run_dir: Path | None = None
    inputs: list[FingerprintArtifactInput] = Field(default_factory=list)
    exact_digest: str
    family_digest: str
    canonical_digest: str = ""
    digest: FingerprintDigest
    assertion_identity: list[str] = Field(default_factory=list)
    terminal_outcome: list[str] = Field(default_factory=list)
    failure_time_characteristics: list[str] = Field(default_factory=list)
    earliest_divergent_signals: list[str] = Field(default_factory=list)
    ranked_divergent_signals: list[str] = Field(default_factory=list)
    ranked_relevant_signals: list[str] = Field(default_factory=list)
    transition_xz_characteristics: list[str] = Field(default_factory=list)
    mapped_sources: list[str] = Field(default_factory=list)
    driver_dependency_shape: list[str] = Field(default_factory=list)
    unresolved_markers: list[str] = Field(default_factory=list)
    ambiguous_markers: list[str] = Field(default_factory=list)
    graph_shape: list[str] = Field(default_factory=list)
    canonical_divergence: list[str] = Field(default_factory=list)
    components: list[FingerprintComponent] = Field(default_factory=list)
    canonical_components: list[FingerprintComponent] = Field(default_factory=list)
    insufficient_evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    parser_notes: list[str] = Field(default_factory=list)


class FingerprintComponentComparison(BaseModel):
    component: str
    match: bool
    left: list[str] = Field(default_factory=list)
    right: list[str] = Field(default_factory=list)


class FingerprintComparisonReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = FINGERPRINT_COMPARISON_SCHEMA_VERSION
    left_path: Path
    right_path: Path
    match_kind: FingerprintMatchKind
    exact_match: bool
    family_match: bool
    canonical_match: bool = False
    component_matches: list[FingerprintComponentComparison] = Field(default_factory=list)
    summary: str
    warnings: list[str] = Field(default_factory=list)
    parser_notes: list[str] = Field(default_factory=list)
