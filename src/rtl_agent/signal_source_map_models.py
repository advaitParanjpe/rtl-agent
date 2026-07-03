from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

SIGNAL_SOURCE_MAP_SCHEMA_VERSION = 1


class SignalMappingStatus(StrEnum):
    EXACT = "exact"
    PROBABLE = "probable"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


class DeclarationCandidate(BaseModel):
    declaration_name: str
    declaration_kind: str
    file_path: str
    line: int
    matched_element: str
    matched_role: str
    match_reason: str
    score: int = Field(ge=0)
    primary: bool = False


class SignalSourceMapping(BaseModel):
    signal: str
    leaf: str
    scope: list[str] = Field(default_factory=list)
    status: SignalMappingStatus
    reason: str
    candidates: list[DeclarationCandidate] = Field(default_factory=list)


class SignalSourceMapReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = SIGNAL_SOURCE_MAP_SCHEMA_VERSION
    repository_map_path: Path
    waveform_slice_path: Path | None = None
    comparison_path: Path | None = None
    total_signals: int = Field(ge=0)
    exact_count: int = Field(ge=0)
    probable_count: int = Field(ge=0)
    ambiguous_count: int = Field(ge=0)
    unresolved_count: int = Field(ge=0)
    mappings: list[SignalSourceMapping] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    parser_notes: list[str] = Field(default_factory=list)
