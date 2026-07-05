"""Pilot the pipeline on genuinely simulator-generated AXI failure waveforms.

Unlike the other AXI checks, whose VCDs are hand-authored, this check compiles a
small checked-in design and testbench with an open-source simulator (Icarus
Verilog) and runs it twice from the same stimulus: once clean and once with a
compile-time-defined seeded fault. The two runs produce a genuine passing-vs-
failing VCD pair, which is then fed through the *real* existing pipeline (the
``run-failure-intelligence`` orchestrator plus ``inspect-run`` and
``export-failure-package``).

The simulator is a fixture-generation/dev dependency only. When ``iverilog`` and
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

from rtl_agent.failure_report_models import FailureReport
from rtl_agent.rtl_driver_trace_models import RtlDriverTraceReport
from rtl_agent.signal_source_map_models import SignalSourceMapReport
from rtl_agent.waveform_comparison_models import WaveformComparisonReport

SIM = ROOT / "examples" / "axi-router-sim"
RTL_DIR = SIM / "rtl"
DESIGN = RTL_DIR / "axi_pipe.sv"
TESTBENCH = SIM / "tb" / "axi_pipe_tb.sv"

DESIGN_FILE = "axi_pipe.sv"
FAILURE_TIME = 45
DIVERGENT_REG = "axi_pipe_tb.axi_pipe.payload_reg"
DIVERGENT_OUT = "axi_pipe_tb.axi_pipe.payload_out"


def main() -> int:
    iverilog = shutil.which("iverilog")
    vvp = shutil.which("vvp")
    if iverilog is None or vvp is None:
        print("axi router simulated-failure check skipped (iverilog/vvp not available)")
        return 0

    with tempfile.TemporaryDirectory(prefix="rtl-agent-axi-sim-") as raw_tmp:
        workspace = Path(raw_tmp)
        passing_vcd = _generate_vcd(iverilog, vvp, workspace, inject_fault=False)
        failing_vcd = _generate_vcd(iverilog, vvp, workspace, inject_fault=True)
        # The two runs must actually differ, proving the seeded fault manifested.
        assert passing_vcd.read_bytes() != failing_vcd.read_bytes()

        run_root = workspace / ".rtl-agent" / "runs"
        run_id = "axi-router-sim-pilot"
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
                str(ROOT / "examples" / "axi-router-sim-agent.yaml"),
                "--failure-time",
                str(FAILURE_TIME),
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

        _check_divergence(run_dir)
        _check_mapping(run_dir)
        _check_driver_evidence(run_dir)
        _check_failure_report(run_dir)
        _check_inspection_and_package(run_dir, workspace)

    print("axi router simulated-failure check passed")
    return 0


def _generate_vcd(iverilog: str, vvp: str, workspace: Path, *, inject_fault: bool) -> Path:
    label = "failure" if inject_fault else "passing"
    binary = workspace / f"{label}.vvp"
    vcd = workspace / f"{label}.vcd"
    compile_args = [iverilog, "-g2012", "-o", str(binary)]
    if inject_fault:
        compile_args.append("-DINJECT_FAULT")
    compile_args.extend([str(DESIGN), str(TESTBENCH)])
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
    # The held payload register and the routed output both corrupt at t=45.
    for name in (DIVERGENT_REG, DIVERGENT_OUT):
        assert name in diverging, name
        assert diverging[name].first_divergence_time == FAILURE_TIME
        assert diverging[name].xz_difference is True
    # Reset and the handshake inputs stay identical between the two runs.
    assert "axi_pipe_tb.axi_pipe.rst_n" in comparison.identical_signals


def _check_mapping(run_dir: Path) -> None:
    signal_map = SignalSourceMapReport.model_validate_json(
        (run_dir / "signal-source-map.json").read_text(encoding="utf-8")
    )
    mappings = {mapping.signal: mapping for mapping in signal_map.mappings}
    for name in (DIVERGENT_REG, DIVERGENT_OUT):
        mapping = mappings[name]
        assert mapping.status == "exact"
        assert {candidate.file_path for candidate in mapping.candidates} == {DESIGN_FILE}
        assert any(candidate.declaration_name == "axi_pipe" for candidate in mapping.candidates)


def _check_driver_evidence(run_dir: Path) -> None:
    trace = RtlDriverTraceReport.model_validate_json(
        (run_dir / "driver-trace.json").read_text(encoding="utf-8")
    )
    traced = {signal.signal: signal for signal in trace.traced_signals}
    payload_out = traced[DIVERGENT_OUT]
    assert payload_out.status == "traced"
    assert any(
        driver.file_path == DESIGN_FILE
        and "assign payload_out = payload_reg;" in driver.statement_text
        for driver in payload_out.drivers
    )
    payload_reg = traced[DIVERGENT_REG]
    assert payload_reg.status == "traced"
    assert all(driver.file_path == DESIGN_FILE for driver in payload_reg.drivers)
    # The register's real capture assignment is recovered as textual evidence.
    assert any(
        "payload_reg <= payload_in;" in driver.statement_text for driver in payload_reg.drivers
    )
    edges = {(edge.source_signal, edge.depends_on) for edge in trace.dependency_edges}
    assert ("payload_out", "payload_reg") in edges


def _check_failure_report(run_dir: Path) -> None:
    report = FailureReport.model_validate_json(
        (run_dir / "failure-report.json").read_text(encoding="utf-8")
    )
    assert report.earliest_divergence_time == FAILURE_TIME
    assert "payload_reg" in report.earliest_divergence_signals
    location_files = {location.file_path for location in report.candidate_source_locations}
    assert location_files == {DESIGN_FILE}
    assert "never identifies a root cause" in " ".join(report.parser_notes).lower()


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
