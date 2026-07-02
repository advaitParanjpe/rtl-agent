from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

REVIEW_REPORT_SCHEMA_VERSION = 1


class ReviewOutcome(StrEnum):
    ACCEPTABLE = "acceptable"
    UNACCEPTABLE = "unacceptable"


class ReviewFindingSource(StrEnum):
    DETERMINISTIC = "deterministic"
    PROVIDER = "provider"


class ReviewFindingSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class EvidenceCitation(BaseModel):
    artifact: Path
    detail: str


class ReviewFinding(BaseModel):
    finding_id: str
    source: ReviewFindingSource
    severity: ReviewFindingSeverity
    title: str
    description: str
    evidence: list[EvidenceCitation] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_uncited_findings(self) -> ReviewFinding:
        if not self.evidence:
            raise ValueError("review findings must cite concrete evidence")
        return self


class ReviewReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = REVIEW_REPORT_SCHEMA_VERSION
    outcome: ReviewOutcome
    task_contract_path: Path
    repository_map_path: Path
    implementation_report_path: Path
    diff_path: Path | None = None
    triage_report_path: Path | None = None
    deterministic_findings: list[ReviewFinding] = Field(default_factory=list)
    provider_findings: list[ReviewFinding] = Field(default_factory=list)
    checked_acceptance_criteria: list[str] = Field(default_factory=list)
    checked_files: list[str] = Field(default_factory=list)
    summary: str
