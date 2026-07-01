from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field
from pathlib import Path

from rtl_agent.config import DiscoveryConfig
from rtl_agent.discovery.classifier import classify_file, is_relevant_path
from rtl_agent.repository_map import FileRecord, ScanStatistics

DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "build",
    "dist",
    "out",
    "coverage",
    ".rtl-agent",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
}
DEFAULT_EXCLUDED_SUFFIXES = {
    ".vcd",
    ".fst",
    ".fsdb",
    ".wlf",
    ".ghw",
    ".log",
    ".tmp",
    ".o",
    ".a",
    ".so",
    ".dylib",
    ".exe",
    ".pyc",
}


@dataclass
class ScannedTextFile:
    path: Path
    relative_path: str
    size_bytes: int
    text: str
    record: FileRecord


@dataclass
class ScanResult:
    files: list[ScannedTextFile] = field(default_factory=list)
    records: list[FileRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: ScanStatistics = field(default_factory=ScanStatistics)


class RepositoryScanner:
    def __init__(self, repo_root: Path, config: DiscoveryConfig) -> None:
        self.repo_root = repo_root.resolve()
        self.config = config

    def scan(self) -> ScanResult:
        result = ScanResult()
        if not self.repo_root.exists() or not self.repo_root.is_dir():
            raise ValueError(f"repository path is not a directory: {self.repo_root}")

        for current, dirnames, filenames in os.walk(
            self.repo_root, topdown=True, followlinks=False
        ):
            current_path = Path(current)
            result.stats.directories_seen += 1
            safe_dirs: list[str] = []
            for dirname in sorted(dirnames):
                dir_path = current_path / dirname
                rel = self._relative_posix(dir_path)
                if dir_path.is_symlink():
                    result.stats.files_skipped += 1
                    result.stats.skipped_symlink += 1
                    result.warnings.append(f"skipped symlinked directory: {rel}")
                    continue
                if self._is_excluded_dir(dirname, rel):
                    result.stats.files_skipped += 1
                    result.stats.skipped_excluded += 1
                    continue
                safe_dirs.append(dirname)
            dirnames[:] = safe_dirs

            for filename in sorted(filenames):
                if result.stats.files_seen >= self.config.max_file_count:
                    result.warnings.append(
                        f"maximum file count reached: {self.config.max_file_count}"
                    )
                    return self._finish(result)
                result.stats.files_seen += 1
                path = current_path / filename
                rel = self._relative_posix(path)
                self._scan_file(path, rel, result)

        return self._finish(result)

    def _scan_file(self, path: Path, rel: str, result: ScanResult) -> None:
        if path.is_symlink():
            target = path.resolve(strict=False)
            if not target.is_relative_to(self.repo_root):
                result.stats.files_skipped += 1
                result.stats.skipped_symlink += 1
                result.warnings.append(f"skipped symlinked file outside repository: {rel}")
                return
        if self._is_excluded_file(path, rel):
            result.stats.files_skipped += 1
            result.stats.skipped_excluded += 1
            return
        if not is_relevant_path(Path(rel)):
            return
        try:
            size = path.stat().st_size
        except OSError as exc:
            result.stats.files_skipped += 1
            result.warnings.append(f"could not stat {rel}: {exc}")
            return
        if size > self.config.max_text_file_bytes:
            result.stats.files_skipped += 1
            result.stats.skipped_oversized += 1
            result.warnings.append(f"skipped oversized relevant file: {rel}")
            return
        try:
            raw = path.read_bytes()
        except OSError as exc:
            result.stats.files_skipped += 1
            result.warnings.append(f"could not read {rel}: {exc}")
            return
        if b"\x00" in raw[:4096]:
            result.stats.files_skipped += 1
            result.stats.skipped_binary += 1
            result.warnings.append(f"skipped binary relevant file: {rel}")
            return
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
            result.warnings.append(f"decoded relevant file with replacement characters: {rel}")
        categories = classify_file(Path(rel), text[:8192])
        record = FileRecord(path=rel, categories=categories, size_bytes=size)
        result.records.append(record)
        result.files.append(
            ScannedTextFile(path=path, relative_path=rel, size_bytes=size, text=text, record=record)
        )
        result.stats.files_indexed += 1
        result.stats.relevant_files += 1

    def _finish(self, result: ScanResult) -> ScanResult:
        result.records.sort(key=lambda item: item.path)
        result.files.sort(key=lambda item: item.relative_path)
        result.warnings = sorted(dict.fromkeys(result.warnings))
        return result

    def _relative_posix(self, path: Path) -> str:
        return path.relative_to(self.repo_root).as_posix()

    def _is_excluded_dir(self, dirname: str, rel: str) -> bool:
        return (
            dirname in DEFAULT_EXCLUDED_DIRS
            or self._matches_any(rel, self.config.exclude_patterns)
            or (
                bool(self.config.include_patterns)
                and not self._matches_any(rel, self.config.include_patterns)
                and not any(
                    pattern.startswith(f"{rel}/") for pattern in self.config.include_patterns
                )
            )
        )

    def _is_excluded_file(self, path: Path, rel: str) -> bool:
        if path.suffix.lower() in DEFAULT_EXCLUDED_SUFFIXES:
            return True
        if self._matches_any(rel, self.config.exclude_patterns):
            return True
        return bool(self.config.include_patterns) and not self._matches_any(
            rel, self.config.include_patterns
        )

    @staticmethod
    def _matches_any(path: str, patterns: list[str]) -> bool:
        return any(
            fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(Path(path).name, pattern)
            for pattern in patterns
        )
