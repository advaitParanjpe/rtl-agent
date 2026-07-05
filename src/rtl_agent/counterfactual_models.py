from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

COUNTERFACTUAL_EXPERIMENT_SCHEMA_VERSION = 1

NON_CAUSAL_DISCLAIMER = (
    "This report records the observed outcome of one manual intervention experiment. "
    "It does not establish causality or a root cause: a change in the observed failure "
    "may have many explanations, and only the explicit, cited evidence below is asserted."
)


class InterventionKind(StrEnum):
    PATCH = "patch"
    REPLACE_TEXT = "replace_text"


class CounterfactualOutcome(StrEnum):
    FAILURE_REMOVED = "failure_removed"
    FAILURE_DELAYED = "failure_delayed"
    FAILURE_ADVANCED = "failure_advanced"
    FAILURE_CHANGED = "failure_changed"
    NO_OBSERVABLE_EFFECT = "no_observable_effect"
    NEW_FAILURE_INTRODUCED = "new_failure_introduced"
    EXPERIMENT_FAILED = "experiment_failed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class InterventionSpec(BaseModel):
    kind: InterventionKind
    description: str | None = None
    allowed_files: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    artifact_relative_path: str
    applied: bool = False
    apply_detail: str | None = None
    # replace_text intervention fields (None for patch interventions).
    replace_file: str | None = None
    replace_old: str | None = None
    replace_new: str | None = None


class BaselineReference(BaseModel):
    run_dir: str
    run_id: str | None = None
    manifest_sha256: str | None = None
    failure_report_sha256: str | None = None
    valid: bool = False
    status: str | None = None
    passing_reference: str | None = None
    passing_reference_exists: bool = False


class WorktreeProvenance(BaseModel):
    source_repo: str
    baseline_commit: str | None = None
    worktree_path: str
    removed: bool = False


class ExecutionRecord(BaseModel):
    command_name: str
    argv: list[str] = Field(default_factory=list)
    cwd: str
    status: str
    exit_code: int | None = None
    duration_seconds: float = Field(ge=0)
    timeout_seconds: int = Field(ge=1)
    stdout_relative_path: str | None = None
    stderr_relative_path: str | None = None
    error: str | None = None
    waveform_references: list[str] = Field(default_factory=list)


class FailureIdentity(BaseModel):
    failure_time: int | None = None
    signals: list[str] = Field(default_factory=list)
    assertion_label: str | None = None
    assertion_time: str | None = None
    divergence_present: bool = False


class ObservableDifference(BaseModel):
    field: str
    baseline: str | None = None
    intervention: str | None = None


class GeneratedArtifact(BaseModel):
    role: str
    relative_path: str
    sha256: str | None = None
    size_bytes: int = Field(ge=0)


class CounterfactualExperimentReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = COUNTERFACTUAL_EXPERIMENT_SCHEMA_VERSION
    experiment_id: str
    created_at: datetime
    target_repo: str
    baseline_commit: str | None = None
    baseline: BaselineReference
    intervention: InterventionSpec
    worktree: WorktreeProvenance
    execution: ExecutionRecord | None = None
    baseline_failure: FailureIdentity
    intervention_failure: FailureIdentity
    outcome: CounterfactualOutcome
    observable_differences: list[ObservableDifference] = Field(default_factory=list)
    generated_artifacts: list[GeneratedArtifact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    insufficient_evidence_reasons: list[str] = Field(default_factory=list)
    disclaimer: str = NON_CAUSAL_DISCLAIMER
    parser_notes: list[str] = Field(default_factory=list)
