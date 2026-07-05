from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

FAILURE_FAMILY_CLUSTER_SCHEMA_VERSION = 1


class ClusterStrictness(StrEnum):
    STRICT = "strict"
    PERMISSIVE = "permissive"


class ClusteringInputSummary(BaseModel):
    strictness: ClusterStrictness
    total_inputs: int = Field(ge=0)
    valid_fingerprints: int = Field(ge=0)
    excluded_invalid: int = Field(ge=0)
    duplicate_paths_ignored: int = Field(ge=0)
    derived_from_counterfactual: int = Field(ge=0)
    family_count: int = Field(ge=0)
    exact_duplicate_count: int = Field(ge=0)
    outlier_count: int = Field(ge=0)
    insufficient_evidence_count: int = Field(ge=0)


class MemberReference(BaseModel):
    source_path: str
    origin: str = "fingerprint"
    exact_digest: str
    family_digest: str


class ExactDuplicateSubgroup(BaseModel):
    exact_digest: str
    size: int = Field(ge=1)
    members: list[str] = Field(default_factory=list)


class RepresentativeFingerprint(BaseModel):
    source_path: str
    exact_digest: str
    family_digest: str
    completeness_score: int = Field(ge=0)
    selection_reason: str


class FailureFamilyGroup(BaseModel):
    family_digest: str
    size: int = Field(ge=1)
    is_outlier: bool = False
    description: str
    representative: RepresentativeFingerprint
    members: list[MemberReference] = Field(default_factory=list)
    exact_duplicate_subgroups: list[ExactDuplicateSubgroup] = Field(default_factory=list)
    observed_time_range: list[str] = Field(default_factory=list)
    assertion_identities: list[str] = Field(default_factory=list)
    earliest_divergent_signals_union: list[str] = Field(default_factory=list)
    earliest_divergent_signals_intersection: list[str] = Field(default_factory=list)
    relevant_signals_union: list[str] = Field(default_factory=list)
    relevant_signals_intersection: list[str] = Field(default_factory=list)
    mapped_sources: list[str] = Field(default_factory=list)
    ambiguity_markers: list[str] = Field(default_factory=list)
    insufficient_evidence_markers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RelatedFamilyLink(BaseModel):
    family_a_digest: str
    family_b_digest: str
    match_kind: str
    shared_components: list[str] = Field(default_factory=list)
    differing_components: list[str] = Field(default_factory=list)


class InsufficientEvidenceEntry(BaseModel):
    source_path: str
    exact_digest: str
    family_digest: str
    reasons: list[str] = Field(default_factory=list)


class ExcludedInput(BaseModel):
    source_path: str
    reason: str


class FailureFamilyClusterReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = FAILURE_FAMILY_CLUSTER_SCHEMA_VERSION
    input_summary: ClusteringInputSummary
    families: list[FailureFamilyGroup] = Field(default_factory=list)
    insufficient_evidence: list[InsufficientEvidenceEntry] = Field(default_factory=list)
    outliers: list[str] = Field(default_factory=list)
    related_family_links: list[RelatedFamilyLink] = Field(default_factory=list)
    excluded_inputs: list[ExcludedInput] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    parser_notes: list[str] = Field(default_factory=list)
