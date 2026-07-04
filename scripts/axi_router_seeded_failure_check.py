"""Validate the failure-intelligence pipeline on a seeded AXI-stream-router bug.

This check drives the *real* existing pipeline (the ``run-failure-intelligence``
orchestrator plus ``inspect-run`` and ``export-failure-package``) over compact
checked-in fixtures: an AXI-stream-router RTL fragment that drives real internal
signals, a passing VCD, and a seeded failing VCD in which the locked payload
goes unstable under backpressure. It asserts the pipeline localizes the seeded
divergence to genuine RTL driver evidence without making causal claims.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from _example_check import ROOT, run_cli

from rtl_agent.failure_divergence_graph_models import FailureDivergenceGraphReport
from rtl_agent.failure_report_models import FailureReport
from rtl_agent.relevant_signal_models import RelevantSignalReductionReport
from rtl_agent.rtl_driver_trace_models import RtlDriverTraceReport
from rtl_agent.signal_source_map_models import SignalSourceMapReport
from rtl_agent.waveform_comparison_models import WaveformComparisonReport

AXI = ROOT / "examples" / "axi-stream-router"
AXI_CONFIG = ROOT / "examples" / "axi-stream-router-agent.yaml"
FAILING_VCD = AXI / "waveforms" / "failure.vcd"
PASSING_VCD = AXI / "waveforms" / "passing.vcd"

ROUTER_FILE = "rtl/axi_stream_router.sv"
DIVERGENT_SIGNAL = "tb.axi_stream_router.payload_out"
DIVERGENT_LEAF = "payload_out"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rtl-agent-axi-router-") as raw_tmp:
        workspace = Path(raw_tmp)
        run_root = workspace / ".rtl-agent" / "runs"
        run_id = "axi-router-seeded-failure"

        # 1. Drive the real orchestrated failure-intelligence pipeline.
        summary = run_cli(
            [
                "run-failure-intelligence",
                "--failing-vcd",
                str(FAILING_VCD),
                "--passing-vcd",
                str(PASSING_VCD),
                "--repo",
                str(AXI),
                "--config",
                str(AXI_CONFIG),
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

        _check_comparison(run_dir)
        _check_reduction(run_dir)
        _check_signal_map(run_dir)
        _check_driver_trace(run_dir)
        _check_divergence_graph(run_dir)
        _check_failure_report(run_dir)
        _check_inspection_and_package(run_dir, workspace)

    print("axi router seeded-failure check passed")
    return 0


def _check_comparison(run_dir: Path) -> None:
    comparison = WaveformComparisonReport.model_validate_json(
        (run_dir / "waveform" / "comparison.json").read_text(encoding="utf-8")
    )
    # The seeded payload instability is the earliest divergence, at t=40.
    assert comparison.global_earliest_divergence_time == 40
    diverging = {signal.name: signal for signal in comparison.diverging_signals}
    assert DIVERGENT_SIGNAL in diverging
    payload = diverging[DIVERGENT_SIGNAL]
    assert payload.first_divergence_time == 40
    assert payload.xz_difference is True
    # The state signal diverges strictly later, so payload_out is unambiguously earliest.
    assert diverging["tb.axi_stream_router.state"].first_divergence_time == 50
    # Clock/reset are stable protocol context and must not be flagged as divergent.
    assert "tb.clk" in comparison.identical_signals
    assert "tb.rst_n" in comparison.identical_signals


def _check_reduction(run_dir: Path) -> None:
    reduction = RelevantSignalReductionReport.model_validate_json(
        (run_dir / "reduction" / "report.json").read_text(encoding="utf-8")
    )
    retained = {signal.name for signal in reduction.retained_signals}
    # The divergent payload and the protocol/state signals are ranked as relevant.
    assert DIVERGENT_SIGNAL in retained
    assert "tb.axi_stream_router.state" in retained
    assert "tb.axi_stream_router.packet_locked" in retained


def _check_signal_map(run_dir: Path) -> None:
    signal_map = SignalSourceMapReport.model_validate_json(
        (run_dir / "signal-source-map.json").read_text(encoding="utf-8")
    )
    mappings = {mapping.signal: mapping for mapping in signal_map.mappings}
    payload = mappings[DIVERGENT_SIGNAL]
    # payload_out maps exactly to the router module source file.
    assert payload.status == "exact"
    assert payload.leaf == DIVERGENT_LEAF
    assert any(candidate.file_path == ROUTER_FILE for candidate in payload.candidates)
    assert any(
        candidate.declaration_name == "axi_stream_router" for candidate in payload.candidates
    )


def _check_driver_trace(run_dir: Path) -> None:
    trace = RtlDriverTraceReport.model_validate_json(
        (run_dir / "driver-trace.json").read_text(encoding="utf-8")
    )
    traced = {signal.signal: signal for signal in trace.traced_signals}
    payload = traced[DIVERGENT_SIGNAL]
    # Real continuous-assignment driver evidence is extracted from the RTL.
    assert payload.status == "traced"
    assign_drivers = [driver for driver in payload.drivers if driver.kind == "continuous_assign"]
    assert any(
        driver.file_path == ROUTER_FILE
        and "assign payload_out = payload_reg;" in driver.statement_text
        for driver in assign_drivers
    )
    # A connected dependency chain is recovered: payload_out -> payload_reg -> payload_in.
    edges = {(edge.source_signal, edge.depends_on) for edge in trace.dependency_edges}
    assert ("payload_out", "payload_reg") in edges
    assert ("payload_reg", "payload_in") in edges
    # Ambiguity is preserved: module inputs and localparams are left unresolved.
    assert "payload_in" in trace.unresolved_identifiers
    assert "ready_downstream" in trace.unresolved_identifiers


def _check_divergence_graph(run_dir: Path) -> None:
    graph = FailureDivergenceGraphReport.model_validate_json(
        (run_dir / "divergence-graph.json").read_text(encoding="utf-8")
    )
    assert graph.global_earliest_divergence_time == 40
    assert DIVERGENT_LEAF in graph.root_identifiers
    root_nodes = {node.identifier: node for node in graph.nodes if node.is_root}
    payload_root = root_nodes[DIVERGENT_LEAF]
    assert payload_root.mapping_status == "exact"
    assert payload_root.driver_resolved is True
    assert payload_root.divergence is not None
    assert payload_root.divergence.first_divergence_time == 40
    # The graph is connected with cited edges rooted at the divergent signal.
    assert any(
        edge.source == DIVERGENT_LEAF
        and edge.target == "payload_reg"
        and edge.evidence_file == ROUTER_FILE
        and edge.evidence_line > 0
        for edge in graph.edges
    )
    assert any(edge.source == "payload_reg" and edge.target == "payload_in" for edge in graph.edges)


def _check_failure_report(run_dir: Path) -> None:
    report = FailureReport.model_validate_json(
        (run_dir / "failure-report.json").read_text(encoding="utf-8")
    )
    assert report.earliest_divergence_time == 40
    assert report.earliest_divergence_signals == [DIVERGENT_LEAF]

    ranked = {signal.name for signal in report.ranked_relevant_signals}
    assert DIVERGENT_SIGNAL in ranked

    # The synthesized report carries the correct source location and module.
    payload_locations = [
        location
        for location in report.candidate_source_locations
        if location.identifier == DIVERGENT_LEAF
    ]
    assert payload_locations
    assert all(location.file_path == ROUTER_FILE for location in payload_locations)
    assert any(location.declaration_name == "axi_stream_router" for location in payload_locations)

    # And the textual driver evidence, cited to the exact RTL line.
    payload_drivers = [
        evidence
        for evidence in report.driver_dependency_evidence
        if evidence.source_signal == DIVERGENT_LEAF
    ]
    assert payload_drivers
    assert any(
        evidence.statement_text is not None
        and "assign payload_out = payload_reg;" in evidence.statement_text
        and evidence.evidence_file == ROUTER_FILE
        for evidence in payload_drivers
    )

    # Ambiguity is preserved and no root cause is claimed.
    unresolved = {gap.identifier for gap in report.unresolved_evidence}
    assert "payload_in" in unresolved
    joined_notes = " ".join(report.parser_notes).lower()
    assert "never identifies a root cause" in joined_notes

    markdown = (run_dir / "failure-report.md").read_text(encoding="utf-8")
    assert "assign payload_out = payload_reg;" in markdown
    assert ROUTER_FILE in markdown


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
