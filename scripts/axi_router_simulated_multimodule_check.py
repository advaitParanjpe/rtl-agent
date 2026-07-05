"""Pilot the pipeline on a simulator-generated, hierarchical multi-module failure.

This check combines the two validated threads: it uses a real open-source
simulator (Icarus Verilog) to generate the waveforms, and it does so over a
hierarchical, multi-file design. A top module instantiates two child modules
from separate files (``ingress`` and ``route``) and wires a staged payload
across the module boundary. A compile-time-defined seeded fault corrupts the
staged payload in the ingress child under backpressure; the route child
registers that cross-module signal one cycle later, so the fault propagates into
the observable output.

The generated passing-vs-failing VCD pair is fed through the *real* existing
pipeline (``run-failure-intelligence`` plus ``inspect-run`` and
``export-failure-package``). The check asserts cross-file source mapping and
cross-module driver/dependency reconstruction localize the seeded divergence.

The simulator is a gated fixture-generation/dev dependency: when ``iverilog`` and
``vvp`` are not available the check skips cleanly and returns success, so the
default validation suite stays hermetic. No new analysis behaviour is added.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from _example_check import ROOT, run_cli

from rtl_agent.failure_divergence_graph_models import FailureDivergenceGraphReport
from rtl_agent.failure_report_models import FailureReport
from rtl_agent.rtl_driver_trace_models import RtlDriverTraceReport
from rtl_agent.signal_source_map_models import SignalSourceMapReport
from rtl_agent.waveform_comparison_models import WaveformComparisonReport

SIM = ROOT / "examples" / "axi-router-sim-hier"
RTL_DIR = SIM / "rtl"
RTL_FILES = [RTL_DIR / "ingress.sv", RTL_DIR / "route.sv", RTL_DIR / "top.sv"]
TESTBENCH = SIM / "tb" / "top_tb.sv"

INGRESS_FILE = "ingress.sv"
ROUTE_FILE = "route.sv"
LANE_FILES = {INGRESS_FILE, ROUTE_FILE}

FAILURE_TIME = 45
OUTPUT_TIME = 55
STAGED_SIGNAL = "top_tb.dut.ingress.payload_staged"
STAGED_LEAF = "payload_staged"
OUTPUT_SIGNAL = "top_tb.dut.route.payload_out"
OUTPUT_LEAF = "payload_out"


def main() -> int:
    iverilog = shutil.which("iverilog")
    vvp = shutil.which("vvp")
    if iverilog is None or vvp is None:
        print("axi router simulated multi-module check skipped (iverilog/vvp not available)")
        return 0

    with tempfile.TemporaryDirectory(prefix="rtl-agent-axi-simhier-") as raw_tmp:
        workspace = Path(raw_tmp)
        passing_vcd = _generate_vcd(iverilog, vvp, workspace, inject_fault=False)
        failing_vcd = _generate_vcd(iverilog, vvp, workspace, inject_fault=True)
        assert passing_vcd.read_bytes() != failing_vcd.read_bytes()

        run_root = workspace / ".rtl-agent" / "runs"
        run_id = "axi-router-sim-hier-pilot"
        summary = run_cli(
            [
                "run-failure-intelligence",
                "--failing-vcd",
                str(failing_vcd),
                "--passing-vcd",
                str(passing_vcd),
                "--repo",
                str(RTL_DIR),
                "--config",
                str(ROOT / "examples" / "axi-router-sim-hier-agent.yaml"),
                "--failure-time",
                str(FAILURE_TIME),
                "--before",
                "20",
                "--after",
                "20",
                "--run-root",
                str(run_root),
                "--run-id",
                run_id,
            ]
        )
        assert summary["status"] == "completed", summary
        run_dir = run_root / run_id

        _check_divergence(run_dir)
        _check_cross_file_mapping(run_dir)
        _check_driver_evidence(run_dir)
        _check_divergence_graph(run_dir)
        _check_failure_report(run_dir)
        _check_inspection_and_package(run_dir, workspace)

    print("axi router simulated multi-module check passed")
    return 0


def _generate_vcd(iverilog: str, vvp: str, workspace: Path, *, inject_fault: bool) -> Path:
    label = "failure" if inject_fault else "passing"
    binary = workspace / f"{label}.vvp"
    vcd = workspace / f"{label}.vcd"
    compile_args = [iverilog, "-g2012", "-o", str(binary)]
    if inject_fault:
        compile_args.append("-DINJECT_FAULT")
    compile_args.extend(str(path) for path in [*RTL_FILES, TESTBENCH])
    _run(compile_args, workspace)
    _run([vvp, str(binary), f"+vcd={vcd}"], workspace)
    assert vcd.exists(), f"simulator did not produce {vcd}"
    return vcd


def _run(args: list[str], cwd: Path) -> None:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "\n".join(
                [
                    f"command failed: {' '.join(args)}",
                    f"exit: {result.returncode}",
                    "stdout:",
                    result.stdout[-2000:],
                    "stderr:",
                    result.stderr[-2000:],
                ]
            )
        )


def _check_divergence(run_dir: Path) -> None:
    comparison = WaveformComparisonReport.model_validate_json(
        (run_dir / "waveform" / "comparison.json").read_text(encoding="utf-8")
    )
    assert comparison.global_earliest_divergence_time == FAILURE_TIME
    diverging = {signal.name: signal for signal in comparison.diverging_signals}
    # The staged payload (ingress) diverges first; the routed output follows a
    # cycle later, having propagated across the module boundary.
    assert diverging[STAGED_SIGNAL].first_divergence_time == FAILURE_TIME
    assert diverging[STAGED_SIGNAL].xz_difference is True
    assert diverging[OUTPUT_SIGNAL].first_divergence_time == OUTPUT_TIME
    assert diverging[OUTPUT_SIGNAL].xz_difference is True


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
    assert routed.status == "exact"
    assert {candidate.file_path for candidate in routed.candidates} == {ROUTE_FILE}


def _check_driver_evidence(run_dir: Path) -> None:
    trace = RtlDriverTraceReport.model_validate_json(
        (run_dir / "driver-trace.json").read_text(encoding="utf-8")
    )
    kinds = {driver.kind for signal in trace.traced_signals for driver in signal.drivers}
    # Both real driver forms are recovered somewhere in the design.
    assert "continuous_assign" in kinds
    assert "procedural_assign" in kinds

    traced = {signal.signal: signal for signal in trace.traced_signals}
    routed = traced[OUTPUT_SIGNAL]
    assert routed.status == "traced"
    # The routed output is registered from the cross-module staged payload.
    assert any(
        driver.file_path == ROUTE_FILE
        and driver.kind == "procedural_assign"
        and "payload_out <= payload_staged;" in driver.statement_text
        for driver in routed.drivers
    )

    # The cross-module dependency chain is cited across two different files.
    edges = {
        (edge.source_signal, edge.depends_on): edge.evidence_file for edge in trace.dependency_edges
    }
    assert edges.get((OUTPUT_LEAF, STAGED_LEAF)) == ROUTE_FILE
    assert edges.get((STAGED_LEAF, "data_in")) == INGRESS_FILE


def _check_divergence_graph(run_dir: Path) -> None:
    graph = FailureDivergenceGraphReport.model_validate_json(
        (run_dir / "divergence-graph.json").read_text(encoding="utf-8")
    )
    assert graph.global_earliest_divergence_time == FAILURE_TIME
    root_nodes = {node.identifier: node for node in graph.nodes if node.is_root}
    output_root = root_nodes[OUTPUT_LEAF]
    assert output_root.mapping_status == "exact"
    assert {declaration.file_path for declaration in output_root.declarations} == {ROUTE_FILE}
    staged_root = root_nodes[STAGED_LEAF]
    assert INGRESS_FILE in {declaration.file_path for declaration in staged_root.declarations}
    # The graph connects across files with cited source edges.
    assert any(
        edge.source == OUTPUT_LEAF
        and edge.target == STAGED_LEAF
        and edge.evidence_file == ROUTE_FILE
        for edge in graph.edges
    )
    assert any(
        edge.source == STAGED_LEAF
        and edge.target == "data_in"
        and edge.evidence_file == INGRESS_FILE
        for edge in graph.edges
    )


def _check_failure_report(run_dir: Path) -> None:
    report = FailureReport.model_validate_json(
        (run_dir / "failure-report.json").read_text(encoding="utf-8")
    )
    assert report.earliest_divergence_time == FAILURE_TIME
    assert STAGED_LEAF in report.earliest_divergence_signals
    # Both child source files are cited by the synthesized report.
    location_files = {location.file_path for location in report.candidate_source_locations}
    assert location_files >= LANE_FILES
    evidence_files = {evidence.evidence_file for evidence in report.driver_dependency_evidence}
    assert evidence_files >= LANE_FILES
    assert "never identifies a root cause" in " ".join(report.parser_notes).lower()

    markdown = (run_dir / "failure-report.md").read_text(encoding="utf-8")
    assert INGRESS_FILE in markdown
    assert ROUTE_FILE in markdown


def _check_inspection_and_package(run_dir: Path, workspace: Path) -> None:
    inspection = run_cli(["inspect-run", "--run-dir", str(run_dir)])
    assert inspection["valid"] is True
    assert inspection["invalid_artifacts"] == 0

    package_dir = workspace / "package"
    package = run_cli(
        ["export-failure-package", "--run-dir", str(run_dir), "--output", str(package_dir)]
    )
    assert package["package_status"] == "valid"
    assert package["verified"] is True
    assert (package_dir / "package-manifest.json").exists()


if __name__ == "__main__":
    sys.exit(main())
