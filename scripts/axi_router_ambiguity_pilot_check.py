"""Robustness pilot: the pipeline must preserve ambiguity, not fake confidence.

This check drives the *real* existing pipeline (the ``run-failure-intelligence``
orchestrator plus ``inspect-run`` and ``export-failure-package``) over a compact
hierarchical fixture built to be genuinely ambiguous: a child module ``lane`` is
defined in two separate files and instantiated more than once by the top module,
so the internal signal names (``data_out``, ``data_hold``) are non-unique across
files. A seeded failing VCD corrupts those signals under an instance scope whose
source therefore matches two declarations.

It asserts that source mapping, driver tracing, the divergence graph, and the
synthesized report all preserve multiple candidates and explicitly report the
ambiguity — rather than collapsing to a single false-confident answer — while
still localizing the seeded divergence. No new analysis behaviour is added.
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

REPO = ROOT / "examples" / "axi-router-ambiguity"
REPO_CONFIG = ROOT / "examples" / "axi-router-ambiguity-agent.yaml"
FAILING_VCD = REPO / "waveforms" / "failure.vcd"
PASSING_VCD = REPO / "waveforms" / "passing.vcd"

LANE_RTL = "rtl/lane_rtl.sv"
LANE_SHADOW = "rtl/lane_shadow.sv"
LANE_FILES = {LANE_RTL, LANE_SHADOW}

DIVERGENT_SIGNAL = "tb.dut.lane.data_out"
DIVERGENT_LEAF = "data_out"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rtl-agent-axi-amb-") as raw_tmp:
        workspace = Path(raw_tmp)
        run_root = workspace / ".rtl-agent" / "runs"
        run_id = "axi-router-ambiguity-pilot"

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

        _check_repeated_instances_and_duplicate_declaration(run_dir)
        _check_earliest_divergence(run_dir)
        _check_ambiguous_source_mapping(run_dir)
        _check_multi_candidate_driver_trace(run_dir)
        _check_divergence_graph_preserves_ambiguity(run_dir)
        _check_failure_report_reports_ambiguity(run_dir)
        _check_inspection_and_package(run_dir, workspace)

    print("axi router ambiguity pilot check passed")
    return 0


def _check_repeated_instances_and_duplicate_declaration(run_dir: Path) -> None:
    repository_map = RepositoryMap.model_validate_json(
        (run_dir / "discovery" / "repository-map.json").read_text(encoding="utf-8")
    )
    # `lane` is declared in two separate files and instantiated (repeatedly).
    lane_files = {
        record.path
        for record in repository_map.files
        if record.source is not None
        and any(declaration.name == "lane" for declaration in record.source.declarations)
    }
    assert lane_files == LANE_FILES
    assert "lane" in repository_map.hierarchy.instantiated_types
    duplicate_names = {
        duplicate.name for duplicate in repository_map.hierarchy.duplicate_declarations
    }
    assert "lane" in duplicate_names


def _check_earliest_divergence(run_dir: Path) -> None:
    comparison = WaveformComparisonReport.model_validate_json(
        (run_dir / "waveform" / "comparison.json").read_text(encoding="utf-8")
    )
    assert comparison.global_earliest_divergence_time == 40
    diverging = {signal.name: signal for signal in comparison.diverging_signals}
    assert DIVERGENT_SIGNAL in diverging
    assert diverging[DIVERGENT_SIGNAL].first_divergence_time == 40


def _check_ambiguous_source_mapping(run_dir: Path) -> None:
    signal_map = SignalSourceMapReport.model_validate_json(
        (run_dir / "signal-source-map.json").read_text(encoding="utf-8")
    )
    assert signal_map.ambiguous_count >= 1
    mappings = {mapping.signal: mapping for mapping in signal_map.mappings}
    divergent = mappings[DIVERGENT_SIGNAL]
    # The divergent signal is reported ambiguous, with BOTH candidate files kept.
    assert divergent.status == "ambiguous"
    assert {candidate.file_path for candidate in divergent.candidates} == LANE_FILES


def _check_multi_candidate_driver_trace(run_dir: Path) -> None:
    trace = RtlDriverTraceReport.model_validate_json(
        (run_dir / "driver-trace.json").read_text(encoding="utf-8")
    )
    traced = {signal.signal: signal for signal in trace.traced_signals}
    divergent = traced[DIVERGENT_SIGNAL]
    assert divergent.status == "traced"
    assert divergent.mapping_status == "ambiguous"
    # Driver evidence is preserved from BOTH candidate files, not collapsed to one.
    assert {driver.file_path for driver in divergent.drivers} == LANE_FILES
    # The dependency edge data_out -> data_hold is cited in both files.
    edge_files = {
        edge.evidence_file
        for edge in trace.dependency_edges
        if edge.source_signal == DIVERGENT_LEAF and edge.depends_on == "data_hold"
    }
    assert edge_files == LANE_FILES


def _check_divergence_graph_preserves_ambiguity(run_dir: Path) -> None:
    graph = FailureDivergenceGraphReport.model_validate_json(
        (run_dir / "divergence-graph.json").read_text(encoding="utf-8")
    )
    root_nodes = {node.identifier: node for node in graph.nodes if node.is_root}
    divergent = root_nodes[DIVERGENT_LEAF]
    assert divergent.mapping_status == "ambiguous"
    # Both candidate declarations are preserved on the graph node.
    assert {declaration.file_path for declaration in divergent.declarations} == LANE_FILES


def _check_failure_report_reports_ambiguity(run_dir: Path) -> None:
    report = FailureReport.model_validate_json(
        (run_dir / "failure-report.json").read_text(encoding="utf-8")
    )
    assert DIVERGENT_LEAF in report.earliest_divergence_signals

    # Both ambiguous source locations for the divergent signal are cited.
    divergent_locations = {
        location.file_path
        for location in report.candidate_source_locations
        if location.identifier == DIVERGENT_LEAF
    }
    assert divergent_locations == LANE_FILES
    assert all(
        location.mapping_status == "ambiguous"
        for location in report.candidate_source_locations
        if location.identifier == DIVERGENT_LEAF
    )

    # The ambiguity is called out explicitly, and no root cause is claimed.
    ambiguous_identifiers = {gap.identifier for gap in report.ambiguous_evidence}
    assert DIVERGENT_LEAF in ambiguous_identifiers
    assert "never identifies a root cause" in " ".join(report.parser_notes).lower()

    markdown = (run_dir / "failure-report.md").read_text(encoding="utf-8")
    assert "ambiguous" in markdown.lower()
    assert LANE_RTL in markdown
    assert LANE_SHADOW in markdown


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


if __name__ == "__main__":
    sys.exit(main())
