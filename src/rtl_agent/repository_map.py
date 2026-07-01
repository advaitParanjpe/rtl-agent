from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

REPOSITORY_MAP_SCHEMA_VERSION = 1


class FileCategory(StrEnum):
    RTL_SOURCE = "rtl_source"
    PACKAGE = "package"
    INTERFACE = "interface"
    INCLUDE = "include"
    TESTBENCH = "testbench"
    ASSERTION = "assertion"
    CONSTRAINTS = "constraints"
    BUILD_CONFIG = "build_configuration"
    SCRIPT = "script"
    DOCUMENTATION = "documentation"
    GENERATED_VENDOR = "generated_or_vendor"
    UNKNOWN_RELEVANT = "unknown_relevant_file"


class DeclarationKind(StrEnum):
    MODULE = "module"
    INTERFACE = "interface"
    PACKAGE = "package"
    PROGRAM = "program"
    CHECKER = "checker"


class FlowCategory(StrEnum):
    LINT = "lint"
    COMPILE = "compile"
    SIMULATION = "simulation"
    UNIT_TEST = "unit_test"
    REGRESSION = "regression"
    FORMAL = "formal"
    SYNTHESIS = "synthesis"
    COVERAGE = "coverage"
    FORMATTING = "formatting"
    UNKNOWN = "unknown"


class GitMetadata(BaseModel):
    is_git_repository: bool
    branch: str | None = None
    detached: bool = False
    commit_hash: str | None = None
    dirty: bool | None = None


class ScanStatistics(BaseModel):
    files_seen: int = 0
    directories_seen: int = 0
    files_indexed: int = 0
    files_skipped: int = 0
    skipped_binary: int = 0
    skipped_oversized: int = 0
    skipped_excluded: int = 0
    skipped_symlink: int = 0
    relevant_files: int = 0


class SourceDeclaration(BaseModel):
    kind: DeclarationKind
    name: str
    line: int


class SourceFileInfo(BaseModel):
    declarations: list[SourceDeclaration] = Field(default_factory=list)
    includes: list[str] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list)
    instantiations: list[str] = Field(default_factory=list)


class FileRecord(BaseModel):
    path: str
    categories: list[FileCategory]
    size_bytes: int
    source: SourceFileInfo | None = None


class DuplicateDeclaration(BaseModel):
    kind: DeclarationKind
    name: str
    locations: list[str]


class TopCandidate(BaseModel):
    name: str
    score: int
    reasons: list[str]
    declaration_path: str
    declaration_line: int
    is_testbench: bool = False


class HierarchyInfo(BaseModel):
    instantiated_types: list[str] = Field(default_factory=list)
    uninstantiated_modules: list[str] = Field(default_factory=list)
    unresolved_instantiations: list[str] = Field(default_factory=list)
    duplicate_declarations: list[DuplicateDeclaration] = Field(default_factory=list)
    design_top_candidates: list[TopCandidate] = Field(default_factory=list)
    testbench_top_candidates: list[TopCandidate] = Field(default_factory=list)


class DiscoveredCommand(BaseModel):
    source_file: str
    label: str
    command_text: str
    category: FlowCategory
    tool: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str
    line: int


class RepositoryGuidance(BaseModel):
    path: str
    classification: str


class RepositoryMap(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = REPOSITORY_MAP_SCHEMA_VERSION
    tool_version: str
    repository_root: Path
    discovered_at: datetime
    git: GitMetadata
    warnings: list[str] = Field(default_factory=list)
    scan_statistics: ScanStatistics
    files: list[FileRecord]
    hierarchy: HierarchyInfo
    commands: list[DiscoveredCommand]
    guidance: list[RepositoryGuidance]
    parser_notes: list[str] = Field(default_factory=list)
