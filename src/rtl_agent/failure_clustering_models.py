from __future__ import annotations

from pydantic import BaseModel, Field

FAILURE_CLUSTERING_SCHEMA_VERSION = 1

FAILURE_CLUSTER_DISCLAIMER = (
    "Clusters group failures by their observed canonical fingerprint identity. Membership "
    "indicates the same or a closely related observed failure behavior; it is not a claim of a "
    "shared root cause."
)


class FailureClusterMember(BaseModel):
    member_id: str
    canonical_digest: str | None = None
    family_digest: str | None = None
    exact_digest: str | None = None
    earliest_divergent_signals: list[str] = Field(default_factory=list)
    observed_outcome: str | None = None
    artifact_ref: str | None = None
    insufficient: bool = False


class FailureCluster(BaseModel):
    cluster_id: str
    canonical_digest: str | None = None
    insufficient: bool = False
    size: int = Field(ge=1)
    representative_id: str
    representative_reason: str
    members: list[str] = Field(default_factory=list)
    member_artifacts: list[str] = Field(default_factory=list)
    family_digests: list[str] = Field(default_factory=list)
    earliest_divergent_signals: list[str] = Field(default_factory=list)
    observed_outcome_distribution: dict[str, int] = Field(default_factory=dict)
    related_cluster_ids: list[str] = Field(default_factory=list)


class FailureClusterReport(BaseModel):
    schema_version: int = FAILURE_CLUSTERING_SCHEMA_VERSION
    total_failures: int = Field(ge=0)
    cluster_count: int = Field(ge=0)
    canonical_cluster_count: int = Field(ge=0)
    insufficient_count: int = Field(ge=0)
    clusters: list[FailureCluster] = Field(default_factory=list)
    assignments: dict[str, str] = Field(default_factory=dict)
    unclustered_member_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str = FAILURE_CLUSTER_DISCLAIMER
    parser_notes: list[str] = Field(default_factory=list)
