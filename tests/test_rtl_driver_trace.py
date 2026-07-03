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
from rtl_agent.rtl_driver_trace import (
    RtlDriverTraceError,
    trace_drivers,
    write_driver_trace,
)
from rtl_agent.signal_source_map import map_signals_to_source, write_signal_source_map


def build(
    tmp_path: Path,
    files: dict[str, tuple[str, list[tuple[str, int]]]],
    signals: list[str],
) -> tuple[Path, Path]:
    """Write RTL files + repository map + signal-source map; return their paths.

    ``files`` maps a repo-relative path to (source_text, [(module_name, line)]).
    """
    root = tmp_path / "repo"
    records: list[FileRecord] = []
    for rel_path, (text, declarations) in files.items():
        absolute = root / rel_path
        absolute.parent.mkdir(parents=True, exist_ok=True)
        absolute.write_text(text, encoding="utf-8")
        records.append(
            FileRecord(
                path=rel_path,
                categories=[FileCategory.RTL_SOURCE],
                size_bytes=len(text),
                source=SourceFileInfo(
                    declarations=[
                        SourceDeclaration(kind=DeclarationKind.MODULE, name=name, line=line)
                        for name, line in declarations
                    ]
                ),
            )
        )
    repo_map = RepositoryMap(
        tool_version="0.1.0",
        repository_root=root,
        discovered_at=utc_now(),
        git=GitMetadata(is_git_repository=False),
        scan_statistics=ScanStatistics(),
        files=records,
        hierarchy=HierarchyInfo(),
        commands=[],
        guidance=[],
    )
    repo_map_path = tmp_path / "repo-map.json"
    repo_map_path.write_text(json.dumps(repo_map.model_dump(mode="json")), encoding="utf-8")
    signal_map = map_signals_to_source(repo_map_path, signal_names=signals)
    signal_map_path = tmp_path / "sigmap.json"
    write_signal_source_map(signal_map, signal_map_path)
    return signal_map_path, repo_map_path


DUT = (
    "module dut (input logic clk, input logic rst_n, output logic valid);\n"
    "    logic a, b;\n"
    "    assign valid = a & b;\n"
    "    always_ff @(posedge clk) begin\n"
    "        if (!rst_n)\n"
    "            a <= 1'b0;\n"
    "        else\n"
    "            a <= b | valid;\n"
    "    end\n"
    "endmodule\n"
)


def test_continuous_assign_driver(tmp_path: Path) -> None:
    sig_map, repo_map = build(tmp_path, {"rtl/dut.sv": (DUT, [("dut", 1)])}, ["dut.valid"])

    report = trace_drivers(sig_map, repo_map, max_depth=1)

    traced = report.traced_signals[0]
    assert traced.signal == "dut.valid"
    assert traced.status == "traced"
    driver = next(d for d in traced.drivers if d.kind == "continuous_assign")
    assert driver.line == 3
    assert driver.lhs_identifiers == ["valid"]
    assert driver.rhs_identifiers == ["a", "b"]
    assert driver.enclosing_declaration == "dut"
    assert driver.label == "textual"


def test_procedural_assign_drivers_are_all_preserved(tmp_path: Path) -> None:
    sig_map, repo_map = build(tmp_path, {"rtl/dut.sv": (DUT, [("dut", 1)])}, ["dut.a"])

    report = trace_drivers(sig_map, repo_map, max_depth=1)

    procedural = [d for d in report.traced_signals[0].drivers if d.kind == "procedural_assign"]
    assert [d.line for d in procedural] == [6, 8]  # both drivers, never collapsed
    assert procedural[0].guard == "if (!rst_n)"
    assert procedural[1].guard == "else"
    # Based literal 1'b0 does not leak a spurious identifier.
    assert procedural[0].rhs_identifiers == []
    assert procedural[1].rhs_identifiers == ["b", "valid"]


def test_port_connection_is_inferred_textual(tmp_path: Path) -> None:
    top = "module top;\n    child u_child (\n        .clk(clk)\n    );\nendmodule\n"
    sig_map, repo_map = build(tmp_path, {"rtl/top.sv": (top, [("top", 1)])}, ["top.clk"])

    report = trace_drivers(sig_map, repo_map, max_depth=1)

    traced = report.traced_signals[0]
    port = next(d for d in traced.drivers if d.kind == "port_connection")
    assert port.line == 3
    assert port.lhs_identifiers == ["clk"]
    assert port.label == "inferred_textual"


def test_dependency_expansion_edges_and_unresolved(tmp_path: Path) -> None:
    sig_map, repo_map = build(tmp_path, {"rtl/dut.sv": (DUT, [("dut", 1)])}, ["dut.valid"])

    report = trace_drivers(sig_map, repo_map, max_depth=2, max_nodes=32)

    edges = {(e.source_signal, e.depends_on) for e in report.dependency_edges}
    assert ("valid", "a") in edges
    assert ("valid", "b") in edges
    assert ("a", "valid") in edges
    # 'b' has no driver -> unresolved, preserved honestly.
    assert "b" in report.unresolved_identifiers
    nodes = {n.identifier: n for n in report.dependency_nodes}
    assert nodes["valid"].resolved is True
    assert nodes["b"].resolved is False


def test_depth_zero_records_no_edges(tmp_path: Path) -> None:
    sig_map, repo_map = build(tmp_path, {"rtl/dut.sv": (DUT, [("dut", 1)])}, ["dut.valid"])

    report = trace_drivers(sig_map, repo_map, max_depth=0)

    assert report.dependency_edges == []
    assert [n.identifier for n in report.dependency_nodes] == ["valid"]


def test_node_limit_truncates(tmp_path: Path) -> None:
    sig_map, repo_map = build(tmp_path, {"rtl/dut.sv": (DUT, [("dut", 1)])}, ["dut.valid"])

    report = trace_drivers(sig_map, repo_map, max_depth=5, max_nodes=1)

    assert report.truncated is True
    assert any("truncated" in warning for warning in report.warnings)


def test_signal_with_no_drivers(tmp_path: Path) -> None:
    text = "module m;\n    logic idle;\nendmodule\n"
    sig_map, repo_map = build(tmp_path, {"rtl/m.sv": (text, [("m", 1)])}, ["m.idle"])

    report = trace_drivers(sig_map, repo_map)

    traced = report.traced_signals[0]
    assert traced.status == "no_drivers"
    assert traced.drivers == []


def test_unmapped_signal_is_reported(tmp_path: Path) -> None:
    text = "module m;\nendmodule\n"
    sig_map, repo_map = build(tmp_path, {"rtl/m.sv": (text, [("m", 1)])}, ["other.block.sig"])

    report = trace_drivers(sig_map, repo_map)

    traced = report.traced_signals[0]
    assert traced.status == "unmapped"
    assert any("unmapped" in warning for warning in report.warnings)


def test_missing_file_warns(tmp_path: Path) -> None:
    sig_map, repo_map = build(tmp_path, {"rtl/dut.sv": (DUT, [("dut", 1)])}, ["dut.valid"])
    (tmp_path / "repo" / "rtl" / "dut.sv").unlink()

    report = trace_drivers(sig_map, repo_map)

    assert any("could not be read" in warning for warning in report.warnings)
    assert report.traced_signals[0].status == "no_drivers"


def test_deterministic_output(tmp_path: Path) -> None:
    sig_map, repo_map = build(tmp_path, {"rtl/dut.sv": (DUT, [("dut", 1)])}, ["dut.valid", "dut.a"])

    report = trace_drivers(sig_map, repo_map, max_depth=2)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_driver_trace(report, first)
    write_driver_trace(report, second)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    assert json.loads(first.read_text(encoding="utf-8"))["schema_version"] == 1


def test_rejects_malformed_signal_map(tmp_path: Path) -> None:
    _, repo_map = build(tmp_path, {"rtl/dut.sv": (DUT, [("dut", 1)])}, ["dut.valid"])
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")

    with pytest.raises(RtlDriverTraceError, match="could not load signal-source map"):
        trace_drivers(bad, repo_map)
