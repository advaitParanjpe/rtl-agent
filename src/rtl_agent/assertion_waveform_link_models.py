from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

ASSERTION_WAVEFORM_LINK_SCHEMA_VERSION = 1


class LinkedAssertion(BaseModel):
    """The specific assertion finding selected from the triage report."""

    assertion_id: str
    index: int = Field(ge=0)
    source: str
    line: int
    summary: str
    signal_or_label: str | None = None
    time_context: str | None = None


class LinkedWaveform(BaseModel):
    """The compatible VCD waveform associated with the selected assertion."""

    path: str
    resolved_path: Path
    source: str
    line: int


class TimestampConversion(BaseModel):
    """Deterministic conversion of an assertion time into VCD tick units."""

    raw_time_context: str
    parsed_value: str
    parsed_unit: str
    vcd_timescale: str
    assertion_femtoseconds: int = Field(ge=0)
    vcd_tick_femtoseconds: int = Field(ge=1)
    failure_timestamp_ticks: int = Field(ge=0)
    exact: bool


class AssertionWaveformLinkReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = ASSERTION_WAVEFORM_LINK_SCHEMA_VERSION
    triage_report_path: Path
    selected_assertion: LinkedAssertion
    selected_waveform: LinkedWaveform
    timestamp_conversion: TimestampConversion
    window_before: int = Field(ge=0)
    window_after: int = Field(ge=0)
    signal_names: list[str] = Field(default_factory=list)
    signal_prefixes: list[str] = Field(default_factory=list)
    waveform_slice_path: Path
    waveform_slice_sha256: str
    slice_selected_signal_count: int = Field(ge=0)
    slice_value_change_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    unresolved_ambiguities: list[str] = Field(default_factory=list)
    parser_notes: list[str] = Field(default_factory=list)
