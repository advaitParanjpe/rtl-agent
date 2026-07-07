from __future__ import annotations

from pydantic import BaseModel, Field

EXPERIMENT_COMPARISON_SCHEMA_VERSION = 1


class SignalChange(BaseModel):
    baseline_signals: list[str] = Field(default_factory=list)
    result_signals: list[str] = Field(default_factory=list)
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    shared: list[str] = Field(default_factory=list)


class FingerprintRelationship(BaseModel):
    relation: str | None = None
    exact_match: bool = False
    family_match: bool = False
    canonical_match: bool = False


class ExperimentComparison(BaseModel):
    """A deterministic, evidence-backed comparison of one experiment result against
    the original failure (reproduced on the minimized counterexample reference)."""

    schema_version: int = EXPERIMENT_COMPARISON_SCHEMA_VERSION
    intervention_id: str
    template_kind: str | None = None
    confidence: str | None = None
    execution_status: str
    comparable: bool = False
    observed_effect: str = "unknown"
    observed_effect_rationale: str | None = None
    fingerprint: FingerprintRelationship = Field(default_factory=FingerprintRelationship)
    baseline_exact_digest: str | None = None
    result_exact_digest: str | None = None
    baseline_family_digest: str | None = None
    result_family_digest: str | None = None
    baseline_canonical_digest: str | None = None
    result_canonical_digest: str | None = None
    family_changed: bool = False
    canonical_changed: bool = False
    assertion_changed: bool = False
    baseline_failure_time: int | None = None
    result_failure_time: int | None = None
    earliest_divergence_time_change: int | None = None
    signal_change: SignalChange = Field(default_factory=SignalChange)
    minimized_stimulus_digest: str | None = None
    artifact_dir: str | None = None
    summary: str = ""
    unsupported_reasons: list[str] = Field(default_factory=list)
