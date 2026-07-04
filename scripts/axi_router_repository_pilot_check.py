"""Pilot the failure-intelligence pipeline on a multi-file AXI-router repository.

This check drives the *real* existing pipeline (the ``run-failure-intelligence``
orchestrator plus ``inspect-run`` and ``export-failure-package``) over a compact
but hierarchical checked-in RTL repository: a top module (``axi_router``) that
instantiates two child modules (``axi_ingress`` and ``axi_route``) from separate
files and wires a staged payload across the module boundary. A seeded failing
VCD corrupts the staged payload under backpressure, which propagates to the
routed output one cycle later.

It asserts that the current architecture — with no new analysis behaviour —
scales to hierarchical RTL: it resolves signals to the correct child files and
reconstructs the driver/dependency chain across module boundaries.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from _example_check import ROOT, run_cli

from rtl_agent.failure_divergence_graph_models import FailureDivergenceGraphReport
from rtl_agent.failure_report_models import FailureReport
from rtl_agent.repository_map import RepositoryMap
from rtl_agent.rtl_driver_trace_models import RtlDriverTraceReport
from rtl_agent.signal_source_map_models import SignalSourceMapReport
from rtl_agent.waveform_comparison_models import WaveformComparisonReport

REPO = ROOT / "examples" / "axi-router-repo"
REPO_CONFIG = ROOT / "examples" / "axi-router-repo-agent.yaml"
FAILING_VCD = REPO / "waveforms" / "failure.vcd"
PASSING_VCD = REPO / "waveforms" / "passing.vcd"

INGRESS_FILE = "rtl/axi_ingress.sv"
ROUTE_FILE = "rtl/axi_route.sv"
TOP_FILE = "rtl/axi_router.sv"

# The seeded fault corrupts the staged payload (driven in the ingress child) and
# propagates to the routed output (driven in the route child) one cycle later.
STAGED_SIGNAL = "tb.dut.axi_ingress.payload_staged"
STAGED_LEAF = "payload_staged"
OUTPUT_SIGNAL = "tb.dut.axi_route.payload_out"
OUTPUT_LEAF = "payload_out"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rtl-agent-axi-repo-") as raw_tmp:
        workspace = Path(raw_tmp)
        run_root = workspace / ".rtl-agent" / "runs"
        run_id = "axi-router-repo-pilot"

        summary = run_cli(
            [
                "run-failure-intelligence",
                "--failing-vcd",
                str(FAILING_VCD),
                "--passing-vcd",
                str(PASSING_VCD),
                "--repo",
                str(REPO),
                "--config",
                str(REPO_CONFIG),
                "--failure-time",
                "40",
                "--before",
                "15",
                "--after",
                "15",
                "--run-root",
                str(run_root),
                "--run-id",
                run_id,
            ]
        )
        assert summary["status"] == "completed", summary
        run_dir = run_root / run_id

        _check_repository_is_multi_file(run_dir)
        _check_earliest_divergence(run_dir)
        _check_cross_file_mapping(run_dir)
        _check_cross_module_dependency_chain(run_dir)
        _check_divergence_graph_connected_across_files(run_dir)
        _check_failure_report_cites_both_files(run_dir)
        _check_inspection_and_package(run_dir, workspace)

    print("axi router repository pilot check passed")
    return 0


def _check_repository_is_multi_file(run_dir: Path) -> None:
    repository_map = RepositoryMap.model_validate_json(
        (run_dir / "discovery" / "repository-map.json").read_text(encoding="utf-8")
    )
    modules_by_file = {
        record.path: {declaration.name for declaration in record.source.declarations}
        for record in repository_map.files
        if record.source is not None and record.source.declarations
    }
    # The top module and its two children live in three separate files.
    assert modules_by_file.get(TOP_FILE) == {"axi_router"}
    assert modules_by_file.get(INGRESS_FILE) == {"axi_ingress"}
    assert modules_by_file.get(ROUTE_FILE) == {"axi_route"}


def _check_earliest_divergence(run_dir: Path) -> None:
    comparison = WaveformComparisonReport.model_validate_json(
        (run_dir / "waveform" / "comparison.json").read_text(encoding="utf-8")
    )
    assert comparison.global_earliest_divergence_time == 40
    diverging = {signal.name: signal for signal in comparison.diverging_signals}
    # The staged payload (ingress) diverges first; the routed output follows later.
    assert diverging[STAGED_SIGNAL].first_divergence_time == 40
    assert diverging[STAGED_SIGNAL].xz_difference is True
    assert diverging[OUTPUT_SIGNAL].first_divergence_time == 50


def _check_cross_file_mapping(run_dir: Path) -> None:
    signal_map = SignalSourceMapReport.model_validate_json(
        (run_dir / "signal-source-map.json").read_text(encoding="utf-8")
    )
    mappings = {mapping.signal: mapping for mapping in signal_map.mappings}
    staged = mappings[STAGED_SIGNAL]
    routed = mappings[OUTPUT_SIGNAL]
    # Each signal resolves exactly to its own child module in its own file.
    assert staged.status == "exact"
    assert {candidate.file_path for candidate in staged.candidates} == {INGRESS_FILE}
    assert any(candidate.declaration_name == "axi_ingress" for candidate in staged.candidates)
    assert routed.status == "exact"
    assert {candidate.file_path for candidate in routed.candidates} == {ROUTE_FILE}
    assert any(candidate.declaration_name == "axi_route" for candidate in routed.candidates)


def _check_cross_module_dependency_chain(run_dir: Path) -> None:
    trace = RtlDriverTraceReport.model_validate_json(
        (run_dir / "driver-trace.json").read_text(encoding="utf-8")
    )
    edges = {(edge.source_signal, edge.depends_on): edge for edge in trace.dependency_edges}
    # The chain payload_out -> payload_staged -> payload_in crosses module files:
    # the first edge is cited in the route child, the second in the ingress child.
    assert (OUTPUT_LEAF, STAGED_LEAF) in edges
    assert edges[(OUTPUT_LEAF, STAGED_LEAF)].evidence_file == ROUTE_FILE
    assert (STAGED_LEAF, "payload_in") in edges
    assert edges[(STAGED_LEAF, "payload_in")].evidence_file == INGRESS_FILE
    # The two links are cited in two different files: genuine cross-module tracing.
    assert (
        edges[(OUTPUT_LEAF, STAGED_LEAF)].evidence_file
        != edges[(STAGED_LEAF, "payload_in")].evidence_file
    )
    # Module inputs remain unresolved: ambiguity is preserved, no causal leap.
    assert "payload_in" in trace.unresolved_identifiers


def _check_divergence_graph_connected_across_files(run_dir: Path) -> None:
    graph = FailureDivergenceGraphReport.model_validate_json(
        (run_dir / "divergence-graph.json").read_text(encoding="utf-8")
    )
    assert graph.global_earliest_divergence_time == 40
    root_files = {
        node.identifier: {declaration.file_path for declaration in node.declarations}
        for node in graph.nodes
        if node.is_root
    }
    # Roots localize to two different child files.
    assert root_files.get(OUTPUT_LEAF) == {ROUTE_FILE}
    assert root_files.get(STAGED_LEAF) == {INGRESS_FILE}
    # The graph is connected across files: the route output edge points at the
    # ingress-driven staged payload, cited to the route source line.
    assert any(
        edge.source == OUTPUT_LEAF
        and edge.target == STAGED_LEAF
        and edge.evidence_file == ROUTE_FILE
        for edge in graph.edges
    )
    assert any(
        edge.source == STAGED_LEAF
        and edge.target == "payload_in"
        and edge.evidence_file == INGRESS_FILE
        for edge in graph.edges
    )


def _check_failure_report_cites_both_files(run_dir: Path) -> None:
    report = FailureReport.model_validate_json(
        (run_dir / "failure-report.json").read_text(encoding="utf-8")
    )
    assert report.earliest_divergence_time == 40
    assert report.earliest_divergence_signals == [STAGED_LEAF]

    location_files = {
        location.identifier: location.file_path for location in report.candidate_source_locations
    }
    assert location_files.get(OUTPUT_LEAF) == ROUTE_FILE
    assert location_files.get(STAGED_LEAF) == INGRESS_FILE

    evidence_files = {
        (evidence.source_signal, evidence.depends_on): evidence.evidence_file
        for evidence in report.driver_dependency_evidence
    }
    assert evidence_files.get((OUTPUT_LEAF, STAGED_LEAF)) == ROUTE_FILE
    assert evidence_files.get((STAGED_LEAF, "payload_in")) == INGRESS_FILE

    # No root cause is claimed and ambiguity is preserved.
    assert "payload_in" in {gap.identifier for gap in report.unresolved_evidence}
    assert "never identifies a root cause" in " ".join(report.parser_notes).lower()

    markdown = (run_dir / "failure-report.md").read_text(encoding="utf-8")
    assert INGRESS_FILE in markdown
    assert ROUTE_FILE in markdown


def _check_inspection_and_package(run_dir: Path, workspace: Path) -> None:
    inspection = run_cli(["inspect-run", "--run-dir", str(run_dir)])
    assert inspection["valid"] is True
    assert inspection["invalid_artifacts"] == 0
    assert inspection["missing_artifacts"] == 0

    package_dir = workspace / "package"
    package = run_cli(
        ["export-failure-package", "--run-dir", str(run_dir), "--output", str(package_dir)]
    )
    assert package["package_status"] == "valid"
    assert package["verified"] is True
    assert (package_dir / "package-manifest.json").exists()
    # The package carries evidence artifacts, not raw RTL sources.
    assert not list(package_dir.rglob("*.sv"))


if __name__ == "__main__":
    sys.exit(main())
