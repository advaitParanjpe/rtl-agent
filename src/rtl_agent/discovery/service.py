from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from rtl_agent import __version__
from rtl_agent.config import DiscoveryConfig
from rtl_agent.discovery.build_discovery import discover_build_commands
from rtl_agent.discovery.classifier import BUILD_EXTENSIONS, DOC_PREFIXES
from rtl_agent.discovery.hierarchy import infer_hierarchy
from rtl_agent.discovery.scanner import RepositoryScanner
from rtl_agent.discovery.sv_parser import parse_systemverilog
from rtl_agent.repository_map import (
    DiscoveredCommand,
    GitMetadata,
    RepositoryGuidance,
    RepositoryMap,
)


class DiscoveryError(RuntimeError):
    pass


def discover_repository(repo_root: Path, config: DiscoveryConfig | None = None) -> RepositoryMap:
    resolved = repo_root.resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise DiscoveryError(f"repository path is not a directory: {resolved}")
    discovery_config = config or DiscoveryConfig()
    scan = RepositoryScanner(resolved, discovery_config).scan()

    commands: list[DiscoveredCommand] = []
    build_texts: list[str] = []
    guidance: list[RepositoryGuidance] = []
    warnings = list(scan.warnings)

    for scanned in scan.files:
        rel_path = Path(scanned.relative_path)
        if rel_path.suffix.lower() in {".v", ".sv", ".vh", ".svh"}:
            parsed = parse_systemverilog(scanned.text)
            scanned.record.source = parsed.info
        if _is_build_file(scanned.relative_path):
            commands.extend(discover_build_commands(scanned.relative_path, scanned.text))
            build_texts.append(scanned.text.lower())
        guidance_item = _guidance(scanned.relative_path)
        if guidance_item:
            guidance.append(guidance_item)

    hierarchy = infer_hierarchy(scan.records, build_texts)
    return RepositoryMap(
        tool_version=__version__,
        repository_root=resolved,
        discovered_at=datetime.now(UTC),
        git=_git_metadata(resolved, warnings),
        warnings=sorted(dict.fromkeys(warnings)),
        scan_statistics=scan.stats,
        files=scan.records,
        hierarchy=hierarchy,
        commands=sorted(commands, key=lambda item: (item.source_file, item.line, item.label)),
        guidance=sorted(guidance, key=lambda item: item.path),
        parser_notes=[
            "SystemVerilog parsing is lightweight: comments and strings are masked "
            "before regex extraction.",
            "The parser does not preprocess macros, elaborate generates, resolve "
            "parameters, or prove hierarchy.",
        ],
    )


def write_repository_map(repository_map: RepositoryMap, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(repository_map.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _git_metadata(repo_root: Path, warnings: list[str]) -> GitMetadata:
    top = _git(repo_root, "rev-parse", "--show-toplevel")
    if top is None:
        return GitMetadata(is_git_repository=False)
    is_repo_root = Path(top).resolve() == repo_root
    if not is_repo_root:
        warnings.append("inspected path is inside a Git repository but is not the Git root")
    branch = _git(repo_root, "branch", "--show-current")
    commit = _git(repo_root, "rev-parse", "HEAD")
    status = _git(repo_root, "status", "--porcelain")
    return GitMetadata(
        is_git_repository=True,
        branch=branch or None,
        detached=not bool(branch),
        commit_hash=commit or None,
        dirty=status is not None and bool(status.strip()),
    )


def _git(repo_root: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _is_build_file(path: str) -> bool:
    rel = Path(path)
    return rel.name in {"Makefile", "CMakeLists.txt"} or rel.suffix.lower() in BUILD_EXTENSIONS


def _guidance(path: str) -> RepositoryGuidance | None:
    rel = Path(path)
    lower = rel.name.lower()
    if lower.startswith(DOC_PREFIXES):
        return RepositoryGuidance(path=path, classification="repository instructions or overview")
    if "spec" in lower or "design" in lower:
        return RepositoryGuidance(path=path, classification="design or specification document")
    if _is_build_file(path):
        return RepositoryGuidance(
            path=path, classification="tool configuration or source file list"
        )
    return None
