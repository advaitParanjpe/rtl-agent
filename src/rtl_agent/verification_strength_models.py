from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rtl_agent.review_models import EvidenceCitation

VERIFICATION_STRENGTH_REPORT_SCHEMA_VERSION = 1


class VerificationStrengthLevel(StrEnum):
    INSUFFICIENT = "insufficient"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


class VerificationSignalKind(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    INFO = "info"


class WeakPatternSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class VerificationStrengthSignal(BaseModel):
    signal_id: str
    kind: VerificationSignalKind
    points: int
    title: str
    description: str
    evidence: list[EvidenceCitation] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_uncited_signals(self) -> VerificationStrengthSignal:
        if not self.evidence:
            raise ValueError("verification-strength signals must cite concrete evidence")
        return self


class WeakValidationPattern(BaseModel):
    pattern_id: str
    severity: WeakPatternSeverity
    title: str
    description: str
    evidence: list[EvidenceCitation] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_uncited_patterns(self) -> WeakValidationPattern:
        if not self.evidence:
            raise ValueError("weak validation patterns must cite concrete evidence")
        return self


class VerificationStrengthReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = VERIFICATION_STRENGTH_REPORT_SCHEMA_VERSION
    strength: VerificationStrengthLevel
    score: int = Field(ge=0, le=100)
    task_contract_path: Path
    repository_map_path: Path
    implementation_report_path: Path
    review_report_path: Path | None = None
    triage_report_paths: list[Path] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    validation_commands: list[str] = Field(default_factory=list)
    assessed_acceptance_criteria: list[str] = Field(default_factory=list)
    covered_acceptance_criteria: list[str] = Field(default_factory=list)
    signals: list[VerificationStrengthSignal] = Field(default_factory=list)
    weak_patterns: list[WeakValidationPattern] = Field(default_factory=list)
    summary: str
