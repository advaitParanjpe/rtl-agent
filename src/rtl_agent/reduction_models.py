from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

STIMULUS_REDUCTION_SCHEMA_VERSION = 1

REDUCTION_DISCLAIMER = (
    "This report records that a reduced stimulus reproduces the same observed failure family "
    "as the baseline, based only on the failure-fingerprint evidence. Preservation of a failure "
    "family does not prove identical root cause, minimality, or causality."
)


class PreservationClass(StrEnum):
    SAME_FAILURE_EXACT = "same_failure_exact"
    SAME_FAILURE_FAMILY = "same_failure_family"
    DIFFERENT_FAILURE = "different_failure"
    FAILURE_REMOVED = "failure_removed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CANDIDATE_INVALID = "candidate_invalid"
    EXECUTION_FAILED = "execution_failed"
    TIMED_OUT = "timed_out"


# Classifications that count as preserving the counterexample.
PRESERVING_CLASSES = frozenset(
    {PreservationClass.SAME_FAILURE_EXACT, PreservationClass.SAME_FAILURE_FAMILY}
)


class TerminationReason(StrEnum):
    NO_FURTHER_REDUCTION = "no_further_reduction"
    BUDGET_EXHAUSTED = "budget_exhausted"
    ALREADY_MINIMAL = "already_minimal"
    BASELINE_NOT_PRESERVED = "baseline_not_preserved"


class CandidateEvaluation(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    candidate_digest: str
    item_count: int = Field(ge=0)
    retained_item_ids: list[str] = Field(default_factory=list)
    classification: PreservationClass
    preserves: bool
    from_cache: bool = False
    command_status: str | None = None
    command_exit_code: int | None = None
    fingerprint_exact_digest: str | None = None
    fingerprint_family_digest: str | None = None
    artifact_dir: str | None = None
    detail: str | None = None


class SimulatorResultSummary(BaseModel):
    command_name: str
    status: str
    exit_code: int | None = None
    timeout_seconds: int = Field(ge=1)


class StimulusReductionReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = STIMULUS_REDUCTION_SCHEMA_VERSION
    minimization_id: str
    created_at: datetime
    baseline_run: str
    baseline_fingerprint_exact_digest: str
    baseline_fingerprint_family_digest: str
    target_repo: str
    target_commit: str | None = None
    command_name: str
    original_stimulus: str
    original_stimulus_digest: str
    minimized_stimulus: str
    minimized_stimulus_digest: str
    original_item_count: int = Field(ge=0)
    minimized_item_count: int = Field(ge=0)
    retained_item_ids: list[str] = Field(default_factory=list)
    removed_item_ids: list[str] = Field(default_factory=list)
    final_classification: PreservationClass
    total_evaluations: int = Field(ge=0)
    cache_hits: int = Field(ge=0)
    evaluation_budget: int = Field(ge=1)
    termination_reason: TerminationReason
    evaluation_history: list[CandidateEvaluation] = Field(default_factory=list)
    simulator_result: SimulatorResultSummary | None = None
    reproducibility_instructions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    insufficient_evidence_reasons: list[str] = Field(default_factory=list)
    disclaimer: str = REDUCTION_DISCLAIMER
    parser_notes: list[str] = Field(default_factory=list)
