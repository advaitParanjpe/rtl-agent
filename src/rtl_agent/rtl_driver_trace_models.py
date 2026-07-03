from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

RTL_DRIVER_TRACE_SCHEMA_VERSION = 1


class StatementKind(StrEnum):
    CONTINUOUS_ASSIGN = "continuous_assign"
    PROCEDURAL_ASSIGN = "procedural_assign"
    PORT_CONNECTION = "port_connection"
    OTHER_REFERENCE = "other_reference"


class EvidenceLabel(StrEnum):
    TEXTUAL = "textual"
    INFERRED_TEXTUAL = "inferred_textual"


class TraceStatus(StrEnum):
    TRACED = "traced"
    NO_DRIVERS = "no_drivers"
    UNMAPPED = "unmapped"


class DriverStatement(BaseModel):
    file_path: str
    line: int
    kind: StatementKind
    label: EvidenceLabel
    statement_text: str
    lhs_identifiers: list[str] = Field(default_factory=list)
    rhs_identifiers: list[str] = Field(default_factory=list)
    enclosing_declaration: str | None = None
    guard: str | None = None


class TracedSignal(BaseModel):
    signal: str
    leaf: str
    status: TraceStatus
    mapping_status: str
    searched_files: list[str] = Field(default_factory=list)
    drivers: list[DriverStatement] = Field(default_factory=list)


class DependencyEdge(BaseModel):
    source_signal: str
    depends_on: str
    label: EvidenceLabel
    statement_kind: StatementKind
    evidence_file: str
    evidence_line: int


class TraceNode(BaseModel):
    identifier: str
    depth: int = Field(ge=0)
    resolved: bool
    driver_count: int = Field(ge=0)


class RtlDriverTraceReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = RTL_DRIVER_TRACE_SCHEMA_VERSION
    signal_source_map_path: Path
    repository_map_path: Path
    repository_root: Path
    max_depth: int = Field(ge=0)
    max_nodes: int = Field(ge=1)
    traced_signals: list[TracedSignal] = Field(default_factory=list)
    dependency_nodes: list[TraceNode] = Field(default_factory=list)
    dependency_edges: list[DependencyEdge] = Field(default_factory=list)
    unresolved_identifiers: list[str] = Field(default_factory=list)
    truncated: bool = False
    warnings: list[str] = Field(default_factory=list)
    parser_notes: list[str] = Field(default_factory=list)
