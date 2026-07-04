from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

FAILURE_DIVERGENCE_GRAPH_SCHEMA_VERSION = 1


class NodeDivergence(BaseModel):
    first_divergence_time: int | None = None
    failing_value: str | None = None
    passing_value: str | None = None
    divergence_score: int = Field(ge=0)
    xz_difference: bool = False


class NodeDeclaration(BaseModel):
    declaration_name: str
    declaration_kind: str
    file_path: str
    line: int


class GraphNode(BaseModel):
    identifier: str
    depth: int = Field(ge=0)
    is_root: bool
    signal: str | None = None
    mapping_status: str | None = None
    driver_resolved: bool | None = None
    driver_count: int | None = None
    divergence: NodeDivergence | None = None
    declarations: list[NodeDeclaration] = Field(default_factory=list)


class GraphEdge(BaseModel):
    source: str
    target: str
    label: str
    statement_kind: str
    evidence_file: str
    evidence_line: int


class FailureDivergenceGraphReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = FAILURE_DIVERGENCE_GRAPH_SCHEMA_VERSION
    comparison_path: Path
    signal_source_map_path: Path
    driver_trace_path: Path
    max_depth: int = Field(ge=0)
    max_nodes: int = Field(ge=1)
    root_identifiers: list[str] = Field(default_factory=list)
    global_earliest_divergence_time: int | None = None
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    unresolved_identifiers: list[str] = Field(default_factory=list)
    truncated: bool = False
    warnings: list[str] = Field(default_factory=list)
    parser_notes: list[str] = Field(default_factory=list)
