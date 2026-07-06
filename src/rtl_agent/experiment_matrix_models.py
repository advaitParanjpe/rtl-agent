from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

EXPERIMENT_MATRIX_SCHEMA_VERSION = 1
INTERVENTION_MANIFEST_SCHEMA_VERSION = 1

MATRIX_DISCLAIMER = (
    "This matrix records the observed effect of each manual intervention on the failure "
    "fingerprint, relative to the baseline. It does not establish causality or a root cause: "
    "only the explicit, cited fingerprint evidence per row is asserted."
)


class ReplaceEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str
    old: str
    new: str


class InterventionEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str = ""
    enabled: bool = True
    allowed_files: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    patch: str | None = None
    replace: ReplaceEdit | None = None


class InterventionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = INTERVENTION_MANIFEST_SCHEMA_VERSION
    interventions: list[InterventionEntry] = Field(default_factory=list)


class MatrixRow(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    intervention_id: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    intervention_digest: str
    experiment_digest: str
    files_affected: list[str] = Field(default_factory=list)
    execution_status: str
    command_status: str | None = None
    simulator_exit_code: int | None = None
    baseline_exact_digest: str
    baseline_family_digest: str
    result_exact_digest: str | None = None
    result_family_digest: str | None = None
    counterfactual_outcome: str | None = None
    fingerprint_relation: str | None = None
    baseline_failure_signals: list[str] = Field(default_factory=list)
    baseline_failure_time: int | None = None
    result_failure_signals: list[str] = Field(default_factory=list)
    result_failure_time: int | None = None
    family_preserved: bool = False
    failure_removed: bool = False
    failure_time_shifted: bool = False
    different_failure: bool = False
    from_cache: bool = False
    warnings: list[str] = Field(default_factory=list)
    insufficient_evidence_reasons: list[str] = Field(default_factory=list)
    artifact_dir: str | None = None
    detail: str | None = None


class MatrixSummary(BaseModel):
    total_requested: int = Field(ge=0)
    executed: int = Field(ge=0)
    skipped: int = Field(ge=0)
    cache_hits: int = Field(ge=0)
    failures_removed: int = Field(ge=0)
    same_family: int = Field(ge=0)
    changed_family: int = Field(ge=0)
    no_effect: int = Field(ge=0)
    infrastructure_failures: int = Field(ge=0)
    insufficient_evidence: int = Field(ge=0)


class ExperimentMatrixReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = EXPERIMENT_MATRIX_SCHEMA_VERSION
    matrix_id: str
    created_at: datetime
    baseline_run: str
    baseline_exact_digest: str
    baseline_family_digest: str
    baseline_failure_signals: list[str] = Field(default_factory=list)
    baseline_failure_time: int | None = None
    reference_exact_digest: str | None = None
    reference_family_digest: str | None = None
    reference_failure_signals: list[str] = Field(default_factory=list)
    reference_failure_time: int | None = None
    reference_artifact_dir: str | None = None
    target_repo: str
    target_commit: str | None = None
    command_name: str
    minimized_stimulus: str
    minimized_stimulus_digest: str
    reduction_report: str
    max_experiments: int = Field(ge=1)
    rows: list[MatrixRow] = Field(default_factory=list)
    summary: MatrixSummary
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str = MATRIX_DISCLAIMER
    parser_notes: list[str] = Field(default_factory=list)
