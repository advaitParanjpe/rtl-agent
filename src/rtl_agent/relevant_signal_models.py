from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

RELEVANT_SIGNAL_REDUCTION_SCHEMA_VERSION = 1


class SignalRelevanceCriterion(StrEnum):
    ASSERTION_NAMED = "assertion_named"
    TRANSITION_AT_FAILURE = "transition_at_failure"
    TRANSITION_IN_WINDOW = "transition_in_window"
    UNKNOWN_OR_HIGHZ = "unknown_or_highz"
    HIERARCHY_PROXIMITY = "hierarchy_proximity"


class SignalRelevanceReason(BaseModel):
    criterion: SignalRelevanceCriterion
    points: int
    detail: str


class RankedSignal(BaseModel):
    name: str
    identifier: str
    score: int = Field(ge=0)
    transition_count: int = Field(ge=0)
    nearest_transition_distance: int | None = None
    reasons: list[SignalRelevanceReason] = Field(default_factory=list)


class ExcludedSignalSummary(BaseModel):
    reason: str
    count: int = Field(ge=0)
    signals: list[str] = Field(default_factory=list)


class RelevantSignalReductionReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = RELEVANT_SIGNAL_REDUCTION_SCHEMA_VERSION
    waveform_slice_path: Path
    assertion_link_path: Path | None = None
    assertion_signal: str | None = None
    assertion_summary: str | None = None
    failure_time: int = Field(ge=0)
    max_signals: int = Field(ge=1)
    total_candidate_signals: int = Field(ge=0)
    retained_signals: list[RankedSignal] = Field(default_factory=list)
    excluded: list[ExcludedSignalSummary] = Field(default_factory=list)
    reduced_slice_path: Path
    reduced_slice_sha256: str
    warnings: list[str] = Field(default_factory=list)
    parser_notes: list[str] = Field(default_factory=list)
