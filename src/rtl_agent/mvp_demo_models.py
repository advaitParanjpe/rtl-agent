from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from rtl_agent.experiment_comparison_models import ExperimentComparison
from rtl_agent.intervention_ranking_models import InterventionRanking

MVP_DEMO_SCHEMA_VERSION = 1

MVP_DEMO_DISCLAIMER = (
    "This summary reports observed experimental results only. It records what each bounded, "
    "reviewable intervention did to the observed failure fingerprint; it does not establish "
    "causality, a root cause, or a proven fix. Every intervention candidate is an evidence-"
    "anchored experiment proposal, not an applied change."
)


class StageRef(BaseModel):
    """A pointer to one workflow stage's produced artifacts."""

    stage: str
    status: str
    reference: str | None = None
    detail: str | None = None


class OriginalFailure(BaseModel):
    failure_run: str
    run_valid: bool
    manifest_status: str | None = None
    family_digest: str | None = None
    exact_digest: str | None = None
    earliest_divergence_time: int | None = None
    earliest_divergence_signals: list[str] = Field(default_factory=list)
    assertion_label: str | None = None
    failure_package: str | None = None
    failure_package_files: int = Field(default=0, ge=0)


class MinimizationSummary(BaseModel):
    reduction_report: str
    original_item_count: int = Field(ge=0)
    minimized_item_count: int = Field(ge=0)
    percent_reduced: int
    final_classification: str
    minimized_stimulus_digest: str


class CandidateSummary(BaseModel):
    candidate_id: str
    template_kind: str
    confidence: str
    file: str
    source_line: int
    affected_signal: str
    hypothesis: str


class ExperimentOutcome(BaseModel):
    intervention_id: str
    template_kind: str | None = None
    confidence: str | None = None
    execution_status: str
    observed_effect: str = "unknown"
    observed_effect_rationale: str | None = None
    counterfactual_outcome: str | None = None
    fingerprint_relation: str | None = None
    failure_removed: bool = False
    different_failure: bool = False
    family_preserved: bool = False
    failure_time_shifted: bool = False
    result_family_digest: str | None = None
    artifact_dir: str | None = None


class Observation(BaseModel):
    intervention_id: str | None = None
    category: str
    statement: str


class NotableEffectGroup(BaseModel):
    label: str
    count: int = Field(ge=0)
    summary: str
    interventions: list[str] = Field(default_factory=list)


class EvidenceReference(BaseModel):
    name: str
    path: str


class NextDebugCheck(BaseModel):
    priority: int = Field(ge=1)
    statement: str
    basis: str


class MvpDemoSummary(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = MVP_DEMO_SCHEMA_VERSION
    demo_id: str
    created_at: datetime
    target_repo: str
    target_commit: str | None = None
    command_name: str
    stages: list[StageRef] = Field(default_factory=list)
    original_failure: OriginalFailure
    minimization: MinimizationSummary
    generated_candidates: list[CandidateSummary] = Field(default_factory=list)
    candidate_counts: dict[str, int] = Field(default_factory=dict)
    experiment_outcomes: list[ExperimentOutcome] = Field(default_factory=list)
    experiment_comparisons: list[ExperimentComparison] = Field(default_factory=list)
    intervention_rankings: list[InterventionRanking] = Field(default_factory=list)
    outcome_counts: dict[str, int] = Field(default_factory=dict)
    observed_effect_counts: dict[str, int] = Field(default_factory=dict)
    observations: list[Observation] = Field(default_factory=list)
    notable_effects: list[NotableEffectGroup] = Field(default_factory=list)
    evidence_references: list[EvidenceReference] = Field(default_factory=list)
    next_debug_checks: list[NextDebugCheck] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str = MVP_DEMO_DISCLAIMER
    parser_notes: list[str] = Field(default_factory=list)
