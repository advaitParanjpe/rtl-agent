from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from rtl_agent.hkg.models import HkgSourceRecord

HKG_STORE_MANIFEST_SCHEMA_VERSION = 1
HKG_GRAPH_FILENAME = "hkg.json"
HKG_MANIFEST_FILENAME = "hkg-manifest.json"
DEFAULT_HKG_ROOT = Path(".rtl-agent/hkg")


class HkgStoreManifest(BaseModel):
    schema_version: int = HKG_STORE_MANIFEST_SCHEMA_VERSION
    graph_file: str = HKG_GRAPH_FILENAME
    graph_schema_version: int
    graph_id: str
    graph_sha256: str
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    source_count: int = Field(ge=0)
    sources: list[HkgSourceRecord] = Field(default_factory=list)


class HkgOperation(StrEnum):
    BUILD = "build"
    UPDATE = "update"


class HkgOperationSummary(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    operation: HkgOperation
    status: str = "valid"
    changed: bool
    graph_root: Path
    graph_sha256: str
    source_count: int = Field(ge=0)
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    canonical_failure_count: int = Field(ge=0)
    intervention_count: int = Field(ge=0)
    experiment_count: int = Field(ge=0)
    observed_effect_count: int = Field(ge=0)
    added_source_ids: list[str] = Field(default_factory=list)
    existing_source_ids: list[str] = Field(default_factory=list)


class HkgInspection(BaseModel):
    valid: bool
    status: str
    graph_root: Path
    graph_path: Path
    manifest_path: Path
    graph_schema_version: int | None = None
    graph_sha256: str | None = None
    manifest_valid: bool = False
    source_count: int = Field(default=0, ge=0)
    source_types: dict[str, int] = Field(default_factory=dict)
    node_count: int = Field(default=0, ge=0)
    edge_count: int = Field(default=0, ge=0)
    canonical_failure_count: int = Field(default=0, ge=0)
    intervention_count: int = Field(default=0, ge=0)
    experiment_count: int = Field(default=0, ge=0)
    observed_effect_count: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)
