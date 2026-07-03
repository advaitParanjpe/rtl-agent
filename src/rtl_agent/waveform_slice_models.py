from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

WAVEFORM_SLICE_SCHEMA_VERSION = 1


class WaveformValueKind(StrEnum):
    SCALAR = "scalar"
    VECTOR = "vector"
    REAL = "real"


class WaveformSignal(BaseModel):
    """A declared VCD variable selected into the slice."""

    name: str
    identifier: str
    var_type: str
    width: int = Field(ge=1)
    kind: WaveformValueKind
    bit_range: str | None = None


class WaveformValueChange(BaseModel):
    """A single value transition preserved inside the requested window."""

    time: int = Field(ge=0)
    signal: str
    identifier: str
    value: str


class WaveformInitialValue(BaseModel):
    """The value in effect at the window start for a selected signal.

    ``determinable`` is false when no value change occurred strictly before the
    requested window start, so the value at the boundary cannot be established
    from the waveform alone.
    """

    signal: str
    identifier: str
    determinable: bool
    value: str | None = None


class WaveformWindow(BaseModel):
    failure_time: int = Field(ge=0)
    before: int = Field(ge=0)
    after: int = Field(ge=0)
    requested_start: int = Field(ge=0)
    requested_end: int = Field(ge=0)
    observed_start: int | None = None
    observed_end: int | None = None


class WaveformParseStatistics(BaseModel):
    scopes: int = Field(ge=0)
    declared_variables: int = Field(ge=0)
    selected_signals: int = Field(ge=0)
    timestamps_total: int = Field(ge=0)
    value_changes_total: int = Field(ge=0)
    value_changes_in_window: int = Field(ge=0)
    truncated: bool = False


class WaveformSourceMetadata(BaseModel):
    path: Path
    size_bytes: int = Field(ge=0)
    sha256: str
    timescale: str | None = None


class WaveformSliceReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = WAVEFORM_SLICE_SCHEMA_VERSION
    source: WaveformSourceMetadata
    window: WaveformWindow
    selected_signals: list[WaveformSignal] = Field(default_factory=list)
    initial_values: list[WaveformInitialValue] = Field(default_factory=list)
    value_changes: list[WaveformValueChange] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    parser_notes: list[str] = Field(default_factory=list)
    parse_statistics: WaveformParseStatistics
