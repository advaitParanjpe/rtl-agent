from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

WAVEFORM_COMPARISON_SCHEMA_VERSION = 1


class TimeBasisKind(StrEnum):
    SHARED_TICKS = "shared_ticks"
    NORMALIZED_FEMTOSECONDS = "normalized_femtoseconds"
    UNNORMALIZED_TICKS = "unnormalized_ticks"


class ComparisonTimeBasis(BaseModel):
    """How the two slices' time axes were reconciled for comparison.

    ``normalized`` records explicitly whether timestamp normalization was
    applied; incompatible traces are never silently aligned.
    """

    kind: TimeBasisKind
    failing_timescale: str | None = None
    passing_timescale: str | None = None
    normalized: bool
    failing_tick_femtoseconds: int | None = None
    passing_tick_femtoseconds: int | None = None
    common_start: int
    common_end: int
    detail: str


class DivergenceInterval(BaseModel):
    start: int
    end: int


class SignalDivergence(BaseModel):
    name: str
    identical: bool
    first_divergence_time: int | None = None
    failing_value_at_divergence: str | None = None
    passing_value_at_divergence: str | None = None
    failing_transition_count: int = Field(ge=0)
    passing_transition_count: int = Field(ge=0)
    xz_difference: bool = False
    divergence_duration: int = Field(ge=0)
    divergence_intervals: list[DivergenceInterval] = Field(default_factory=list)
    divergence_score: int = Field(ge=0)


class WaveformComparisonReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = WAVEFORM_COMPARISON_SCHEMA_VERSION
    failing_slice_path: Path
    passing_slice_path: Path
    time_basis: ComparisonTimeBasis
    shared_signal_count: int = Field(ge=0)
    added_signals: list[str] = Field(default_factory=list)
    removed_signals: list[str] = Field(default_factory=list)
    diverging_signals: list[SignalDivergence] = Field(default_factory=list)
    identical_signals: list[str] = Field(default_factory=list)
    global_earliest_divergence_time: int | None = None
    global_earliest_divergence_signals: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    parser_notes: list[str] = Field(default_factory=list)
