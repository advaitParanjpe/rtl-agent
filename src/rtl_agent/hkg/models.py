from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

HKG_SCHEMA_VERSION = 1

HKG_DISCLAIMER = (
    "The Hardware Knowledge Graph is a deterministic construction over existing structured "
    "evidence artifacts. Nodes and edges record observed structure and observed experimental "
    "effects with provenance back to their source artifacts; they encode no causal or "
    "root-cause claim, and the graph performs no inference or querying."
)


class NodeType(StrEnum):
    MODULE = "module"
    SIGNAL = "signal"
    SOURCE_LOCATION = "source_location"
    FAILURE = "failure"
    CANONICAL_FINGERPRINT = "canonical_fingerprint"
    FAILURE_CLUSTER = "failure_cluster"
    INTERVENTION = "intervention"
    EXPERIMENT = "experiment"
    OBSERVED_EFFECT = "observed_effect"


class EdgeType(StrEnum):
    CONTAINS = "contains"
    DRIVES = "drives"
    DEPENDS_ON = "depends_on"
    ORIGINATED_FROM = "originated_from"
    BELONGS_TO_CLUSTER = "belongs_to_cluster"
    GENERATED = "generated"
    PRODUCED = "produced"
    REFERENCES = "references"


class Provenance(BaseModel):
    """A citation back to the structured artifact a node or edge was built from."""

    model_config = ConfigDict(frozen=True)

    artifact_id: str
    schema_version: int | None = None
    content_sha256: str | None = None
    path: str | None = None


class HkgNode(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    node_id: str
    type: NodeType
    label: str
    attributes: dict[str, str] = Field(default_factory=dict)
    provenance: list[Provenance] = Field(default_factory=list)


class HkgEdge(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    edge_id: str
    type: EdgeType
    source: str
    target: str
    attributes: dict[str, str] = Field(default_factory=dict)
    provenance: list[Provenance] = Field(default_factory=list)


class HkgGraph(BaseModel):
    schema_version: int = HKG_SCHEMA_VERSION
    graph_id: str
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    node_type_counts: dict[str, int] = Field(default_factory=dict)
    edge_type_counts: dict[str, int] = Field(default_factory=dict)
    nodes: list[HkgNode] = Field(default_factory=list)
    edges: list[HkgEdge] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str = HKG_DISCLAIMER
    parser_notes: list[str] = Field(default_factory=list)
