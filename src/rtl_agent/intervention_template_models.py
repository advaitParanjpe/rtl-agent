from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

INTERVENTION_TEMPLATE_SCHEMA_VERSION = 1

TEMPLATE_DISCLAIMER = (
    "Each candidate is an evidence-anchored experiment proposal, not a fix and not a causal "
    "conclusion. It proposes a bounded edit whose observed effect can be measured with the "
    "experiment matrix; the confidence level reflects only how completely the existing evidence "
    "grounds the edit, never the likelihood that the edit fixes the failure."
)


class TemplateKind(StrEnum):
    SUPPRESS_ASSIGNMENT = "suppress_assignment"
    HOLD_REGISTER = "hold_register"
    OVERRIDE_CONDITION = "override_condition"
    BLOCK_STATE_TRANSITION = "block_state_transition"
    BOUNDED_SIGNAL_OVERRIDE = "bounded_signal_override"


class ConfidenceLevel(StrEnum):
    HIGH_EVIDENCE = "high_evidence"
    MODERATE_EVIDENCE = "moderate_evidence"
    LOW_EVIDENCE = "low_evidence"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class DriverAnchor(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    file_path: str
    line: int
    statement_kind: str
    statement_text: str
    guard: str | None = None
    label: str


class EvidenceAnchor(BaseModel):
    """Exact, cited evidence a candidate was derived from."""

    model_config = ConfigDict(use_enum_values=True)

    signal: str
    leaf: str
    mapping_status: str
    divergence_node: str | None = None
    divergence_time: int | None = None
    failing_value: str | None = None
    passing_value: str | None = None
    xz_difference: bool = False
    family_digest: str | None = None
    drivers: list[DriverAnchor] = Field(default_factory=list)


class InterventionCandidate(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    candidate_id: str
    template_kind: TemplateKind
    hypothesis: str
    confidence: ConfidenceLevel
    file: str
    source_file: str
    source_line: int
    source_span_text: str
    source_sha256: str
    file_sha256: str
    replace_old: str
    proposed_replacement: str
    allowed_files: list[str] = Field(default_factory=list)
    affected_signal: str
    affected_condition: str | None = None
    divergence_node: str | None = None
    divergence_time: int | None = None
    evidence: EvidenceAnchor
    semantic_digest: str
    warnings: list[str] = Field(default_factory=list)
    applicability_constraints: list[str] = Field(default_factory=list)
    experiment_note: str


class SkippedSite(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    template_kind: TemplateKind
    signal: str | None = None
    location: str | None = None
    reason: str
    confidence: ConfidenceLevel = ConfidenceLevel.INSUFFICIENT_EVIDENCE


class UnsupportedTemplate(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    template_kind: TemplateKind
    reason: str


class TemplateSummary(BaseModel):
    templates_considered: int = Field(ge=0)
    candidates_emitted: int = Field(ge=0)
    sites_skipped: int = Field(ge=0)
    high_evidence: int = Field(ge=0)
    moderate_evidence: int = Field(ge=0)
    low_evidence: int = Field(ge=0)


class InterventionTemplateReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = INTERVENTION_TEMPLATE_SCHEMA_VERSION
    generation_id: str
    created_at: datetime
    failure_run: str
    baseline_family_digest: str | None = None
    baseline_exact_digest: str | None = None
    target_repo: str
    target_commit: str | None = None
    allowed_files: list[str] = Field(default_factory=list)
    max_candidates: int = Field(ge=1)
    reduction_report: str | None = None
    earliest_divergence_time: int | None = None
    candidates: list[InterventionCandidate] = Field(default_factory=list)
    skipped: list[SkippedSite] = Field(default_factory=list)
    unsupported: list[UnsupportedTemplate] = Field(default_factory=list)
    summary: TemplateSummary
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str = TEMPLATE_DISCLAIMER
    parser_notes: list[str] = Field(default_factory=list)


def candidate_manifest_metadata(candidate: InterventionCandidate) -> dict[str, Any]:
    """The evidence metadata embedded into the experiment-matrix manifest entry."""

    return {
        "candidate_id": candidate.candidate_id,
        "template_kind": str(candidate.template_kind),
        "confidence": str(candidate.confidence),
        "hypothesis": candidate.hypothesis,
        "affected_signal": candidate.affected_signal,
        "affected_condition": candidate.affected_condition,
        "divergence_node": candidate.divergence_node,
        "divergence_time": candidate.divergence_time,
        "source_file": candidate.source_file,
        "source_line": candidate.source_line,
        "source_sha256": candidate.source_sha256,
        "semantic_digest": candidate.semantic_digest,
        "experiment_note": candidate.experiment_note,
    }
