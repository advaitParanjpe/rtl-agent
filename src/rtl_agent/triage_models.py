from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

TRIAGE_REPORT_SCHEMA_VERSION = 1


class TriageSource(StrEnum):
    STDOUT = "stdout"
    STDERR = "stderr"


class TriageEvidence(BaseModel):
    source: TriageSource
    line: int
    text: str


class AssertionFailure(BaseModel):
    source: TriageSource
    line: int
    summary: str
    signal_or_label: str | None = None
    time_context: str | None = None


class WaveformReference(BaseModel):
    source: TriageSource
    line: int
    path: str
    exists: bool
    resolved_path: Path | None = None
    evidence: str


class SimulatorContext(BaseModel):
    source: TriageSource
    line: int
    category: str
    text: str


class TriageReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = TRIAGE_REPORT_SCHEMA_VERSION
    command_name: str
    command_status: str
    command_exit_code: int | None
    command_result_path: Path
    stdout_path: Path
    stderr_path: Path
    assertion_failures: list[AssertionFailure] = Field(default_factory=list)
    waveform_references: list[WaveformReference] = Field(default_factory=list)
    simulator_context: list[SimulatorContext] = Field(default_factory=list)
    bounded_evidence: list[TriageEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    parser_notes: list[str] = Field(default_factory=list)
