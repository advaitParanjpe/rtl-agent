from __future__ import annotations

import json
from pathlib import Path

import pytest

from rtl_agent.models import utc_now
from rtl_agent.repository_map import (
    DeclarationKind,
    FileCategory,
    FileRecord,
    GitMetadata,
    HierarchyInfo,
    RepositoryMap,
    ScanStatistics,
    SourceDeclaration,
    SourceFileInfo,
)
from rtl_agent.signal_source_map import (
    SignalSourceMapError,
    map_signals_to_source,
    write_signal_source_map,
)


def make_repo_map(
    tmp_path: Path, declarations: list[tuple[str, str, DeclarationKind, int]]
) -> Path:
    by_file: dict[str, list[SourceDeclaration]] = {}
    for file_path, name, kind, line in declarations:
        by_file.setdefault(file_path, []).append(SourceDeclaration(kind=kind, name=name, line=line))
    files = [
        FileRecord(
            path=file_path,
            categories=[FileCategory.RTL_SOURCE],
            size_bytes=10,
            source=SourceFileInfo(declarations=decls),
        )
        for file_path, decls in by_file.items()
    ]
    repo_map = RepositoryMap(
        tool_version="0.1.0",
        repository_root=tmp_path / "repo",
        discovered_at=utc_now(),
        git=GitMetadata(is_git_repository=False),
        scan_statistics=ScanStatistics(),
        files=files,
        hierarchy=HierarchyInfo(),
        commands=[],
        guidance=[],
    )
    path = tmp_path / "repo-map.json"
    path.write_text(json.dumps(repo_map.model_dump(mode="json")), encoding="utf-8")
    return path


def test_exact_scope_mapping(tmp_path: Path) -> None:
    repo = make_repo_map(tmp_path, [("rtl/top.sv", "top", DeclarationKind.MODULE, 1)])

    report = map_signals_to_source(repo, signal_names=["top.dut.valid"])

    mapping = report.mappings[0]
    assert mapping.status == "exact"
    assert mapping.leaf == "valid"
    assert mapping.scope == ["top", "dut"]
    primary = [c for c in mapping.candidates if c.primary]
    assert len(primary) == 1
    assert primary[0].declaration_name == "top"
    assert primary[0].file_path == "rtl/top.sv"
    assert primary[0].matched_role == "scope"
    assert report.exact_count == 1


def test_unresolved_when_no_declaration_matches(tmp_path: Path) -> None:
    repo = make_repo_map(tmp_path, [("rtl/top.sv", "top", DeclarationKind.MODULE, 1)])

    report = map_signals_to_source(repo, signal_names=["other.block.sig"])

    mapping = report.mappings[0]
    assert mapping.status == "unresolved"
    assert mapping.candidates == []
    assert report.unresolved_count == 1


def test_ambiguous_preserves_all_candidates(tmp_path: Path) -> None:
    repo = make_repo_map(
        tmp_path,
        [
            ("rtl/a/core.sv", "core", DeclarationKind.MODULE, 3),
            ("rtl/b/core.sv", "core", DeclarationKind.MODULE, 7),
        ],
    )

    report = map_signals_to_source(repo, signal_names=["core.reg_q"])

    mapping = report.mappings[0]
    assert mapping.status == "ambiguous"
    primaries = sorted(c.file_path for c in mapping.candidates if c.primary)
    assert primaries == ["rtl/a/core.sv", "rtl/b/core.sv"]
    assert "multiple declarations" in mapping.reason
    assert report.ambiguous_count == 1


def test_probable_when_only_leaf_matches(tmp_path: Path) -> None:
    # The leaf name coincides with a module declaration; weaker evidence.
    repo = make_repo_map(tmp_path, [("rtl/fifo.sv", "fifo", DeclarationKind.MODULE, 1)])

    report = map_signals_to_source(repo, signal_names=["fifo"])

    mapping = report.mappings[0]
    assert mapping.status == "probable"
    assert mapping.candidates[0].matched_role == "leaf"
    assert report.probable_count == 1


def test_scope_based_disambiguation_prefers_outer_scope(tmp_path: Path) -> None:
    # 'inner' is a duplicated module name, but the outer scope 'top' resolves cleanly.
    repo = make_repo_map(
        tmp_path,
        [
            ("rtl/top.sv", "top", DeclarationKind.MODULE, 1),
            ("rtl/a/inner.sv", "inner", DeclarationKind.MODULE, 2),
            ("rtl/b/inner.sv", "inner", DeclarationKind.MODULE, 4),
        ],
    )

    report = map_signals_to_source(repo, signal_names=["top.inner.sig"])

    mapping = report.mappings[0]
    assert mapping.status == "exact"
    primary = [c for c in mapping.candidates if c.primary]
    assert len(primary) == 1
    assert primary[0].declaration_name == "top"
    # The duplicated 'inner' declarations are still preserved as lower candidates.
    inner = sorted(c.file_path for c in mapping.candidates if c.matched_element == "inner")
    assert inner == ["rtl/a/inner.sv", "rtl/b/inner.sv"]


def test_case_insensitive_match_is_probable(tmp_path: Path) -> None:
    repo = make_repo_map(tmp_path, [("rtl/top.sv", "Top", DeclarationKind.MODULE, 1)])

    report = map_signals_to_source(repo, signal_names=["top.dut.sig"])

    mapping = report.mappings[0]
    assert mapping.status == "probable"
    assert "case-insensitive" in mapping.candidates[0].match_reason


def test_empty_input_warns(tmp_path: Path) -> None:
    repo = make_repo_map(tmp_path, [("rtl/top.sv", "top", DeclarationKind.MODULE, 1)])

    report = map_signals_to_source(repo)

    assert report.mappings == []
    assert any("no signals were provided" in warning for warning in report.warnings)


def test_signals_read_from_waveform_slice(tmp_path: Path) -> None:
    from rtl_agent.waveform import extract_waveform_window, write_waveform_slice

    slice_report = extract_waveform_window(
        Path("examples/waveforms/failure.vcd"), failure_time=40, before=15, after=5
    )
    slice_path = tmp_path / "slice.json"
    write_waveform_slice(slice_report, slice_path)
    repo = make_repo_map(tmp_path, [("rtl/top.sv", "top", DeclarationKind.MODULE, 1)])

    report = map_signals_to_source(repo, waveform_slice_path=slice_path)

    signals = {mapping.signal for mapping in report.mappings}
    assert "top.clk" in signals
    assert "top.dut.valid" in signals
    assert all(mapping.status == "exact" for mapping in report.mappings)


def test_deterministic_output(tmp_path: Path) -> None:
    repo = make_repo_map(
        tmp_path,
        [
            ("rtl/top.sv", "top", DeclarationKind.MODULE, 1),
            ("rtl/a/core.sv", "core", DeclarationKind.MODULE, 3),
            ("rtl/b/core.sv", "core", DeclarationKind.MODULE, 7),
        ],
    )
    report = map_signals_to_source(repo, signal_names=["top.dut.valid", "core.q", "x.y.z"])

    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_signal_source_map(report, first)
    write_signal_source_map(report, second)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    assert json.loads(first.read_text(encoding="utf-8"))["schema_version"] == 1


def test_rejects_malformed_repository_map(tmp_path: Path) -> None:
    bad = tmp_path / "repo-map.json"
    bad.write_text("{}", encoding="utf-8")

    with pytest.raises(SignalSourceMapError, match="could not load repository map"):
        map_signals_to_source(bad, signal_names=["top.a"])
