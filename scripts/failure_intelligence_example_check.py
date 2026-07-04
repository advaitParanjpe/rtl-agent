from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from _example_check import ROOT, run_cli

from rtl_agent.artifacts import RunStore
from rtl_agent.evidence_bundle_models import EvidenceBundleReport
from rtl_agent.failure_divergence_graph_models import FailureDivergenceGraphReport
from rtl_agent.relevant_signal_models import RelevantSignalReductionReport
from rtl_agent.repository_map import RepositoryMap
from rtl_agent.rtl_driver_trace_models import RtlDriverTraceReport
from rtl_agent.signal_source_map_models import SignalSourceMapReport
from rtl_agent.waveform_comparison_models import WaveformComparisonReport
from rtl_agent.waveform_slice_models import WaveformSliceReport

FAILING_VCD = ROOT / "examples" / "waveforms" / "failure.vcd"
PASSING_VCD = ROOT / "examples" / "waveforms" / "passing.vcd"
SIMPLE_RTL = ROOT / "examples" / "simple-rtl"
SIMPLE_RTL_CONFIG = ROOT / "examples" / "simple-rtl-agent.yaml"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rtl-agent-failure-intel-") as raw_tmp:
        workspace = Path(raw_tmp)
        store = RunStore(workspace / ".rtl-agent" / "runs", run_id="failure-intelligence-example")
        store.create()
        run_dir = store.run_dir
        (run_dir / "waveform").mkdir()
        (run_dir / "discovery").mkdir()
        (run_dir / "reduction").mkdir()

        failing_slice_path = run_dir / "waveform" / "failing-slice.json"
        passing_slice_path = run_dir / "waveform" / "passing-slice.json"
        comparison_path = run_dir / "waveform" / "comparison.json"
        repository_map_path = run_dir / "discovery" / "repository-map.json"
        signal_map_path = run_dir / "signal-source-map.json"
        driver_trace_path = run_dir / "driver-trace.json"
        divergence_graph_path = run_dir / "divergence-graph.json"
        reduction_path = run_dir / "reduction" / "report.json"
        reduced_slice_path = run_dir / "reduction" / "reduced-slice.json"
        evidence_bundle_dir = workspace / "bundle"

        # 1. Waveform extraction: a failing slice and a passing reference slice.
        for source, output in (
            (FAILING_VCD, failing_slice_path),
            (PASSING_VCD, passing_slice_path),
        ):
            run_cli(
                [
                    "extract-waveform-window",
                    "--vcd",
                    str(source),
                    "--failure-time",
                    "40",
                    "--before",
                    "15",
                    "--after",
                    "15",
                    "--output",
                    str(output),
                ]
            )
        failing_slice = WaveformSliceReport.model_validate_json(
            failing_slice_path.read_text(encoding="utf-8")
        )
        passing_slice = WaveformSliceReport.model_validate_json(
            passing_slice_path.read_text(encoding="utf-8")
        )
        assert failing_slice.schema_version == 1
        assert passing_slice.schema_version == 1
        assert failing_slice.window.failure_time == 40
        assert failing_slice.window.requested_start == 25
        assert failing_slice.window.requested_end == 55
        slice_signal_names = {signal.name for signal in failing_slice.selected_signals}
        assert slice_signal_names == {"top.clk", "top.data", "top.dut.valid", "top.dut.state"}

        # 2. Relevant-signal reduction over the failing slice.
        run_cli(
            [
                "reduce-signals",
                "--waveform-slice",
                str(failing_slice_path),
                "--output",
                str(reduction_path),
                "--reduced-slice-output",
                str(reduced_slice_path),
            ]
        )
        reduction = RelevantSignalReductionReport.model_validate_json(
            reduction_path.read_text(encoding="utf-8")
        )
        assert reduction.schema_version == 1
        assert reduction.total_candidate_signals == 4
        retained_names = {signal.name for signal in reduction.retained_signals}
        assert retained_names <= slice_signal_names
        assert {"top.dut.state", "top.dut.valid"} <= retained_names
        reduced_slice = WaveformSliceReport.model_validate_json(
            reduced_slice_path.read_text(encoding="utf-8")
        )
        assert {signal.name for signal in reduced_slice.selected_signals} == retained_names

        # 3. Passing/failing comparison.
        run_cli(
            [
                "compare-waveforms",
                "--failing-slice",
                str(failing_slice_path),
                "--passing-slice",
                str(passing_slice_path),
                "--output",
                str(comparison_path),
            ]
        )
        comparison = WaveformComparisonReport.model_validate_json(
            comparison_path.read_text(encoding="utf-8")
        )
        assert comparison.schema_version == 1
        assert comparison.time_basis.kind == "shared_ticks"
        diverging_names = {signal.name for signal in comparison.diverging_signals}
        assert diverging_names == {"top.dut.state", "top.dut.valid"}
        assert {"top.clk", "top.data"} <= set(comparison.identical_signals)
        assert comparison.global_earliest_divergence_time == 25
        assert all(
            signal.first_divergence_time == 25 and signal.xz_difference
            for signal in comparison.diverging_signals
        )

        # 4. Repository discovery.
        run_cli(
            [
                "inspect-repo",
                "--repo",
                str(SIMPLE_RTL),
                "--config",
                str(SIMPLE_RTL_CONFIG),
                "--output",
                str(repository_map_path),
            ]
        )
        repository_map = RepositoryMap.model_validate_json(
            repository_map_path.read_text(encoding="utf-8")
        )
        assert repository_map.schema_version == 1
        declared = {
            declaration.name
            for record in repository_map.files
            if record.source is not None
            for declaration in record.source.declarations
        }
        assert "top" in declared

        # 5. Signal-source mapping for the compared signals.
        run_cli(
            [
                "map-signals",
                "--repository-map",
                str(repository_map_path),
                "--comparison",
                str(comparison_path),
                "--output",
                str(signal_map_path),
            ]
        )
        signal_map = SignalSourceMapReport.model_validate_json(
            signal_map_path.read_text(encoding="utf-8")
        )
        assert signal_map.schema_version == 1
        assert signal_map.total_signals == 4
        assert signal_map.exact_count == 4
        assert all(mapping.status == "exact" for mapping in signal_map.mappings)
        for mapping in signal_map.mappings:
            assert any(candidate.file_path == "rtl/top.sv" for candidate in mapping.candidates)

        # 6. Static driver tracing.
        run_cli(
            [
                "trace-drivers",
                "--signal-source-map",
                str(signal_map_path),
                "--repository-map",
                str(repository_map_path),
                "--output",
                str(driver_trace_path),
            ]
        )
        driver_trace = RtlDriverTraceReport.model_validate_json(
            driver_trace_path.read_text(encoding="utf-8")
        )
        assert driver_trace.schema_version == 1
        traced_status = {signal.signal: signal.status for signal in driver_trace.traced_signals}
        assert traced_status["top.clk"] == "traced"
        assert traced_status["top.dut.state"] == "no_drivers"
        assert traced_status["top.dut.valid"] == "no_drivers"
        clk_traced = next(s for s in driver_trace.traced_signals if s.signal == "top.clk")
        assert any(driver.kind == "port_connection" for driver in clk_traced.drivers)
        assert {"state", "valid"} <= set(driver_trace.unresolved_identifiers)

        # 7. Failure divergence graph composed from the prior artifacts.
        run_cli(
            [
                "divergence-graph",
                "--comparison",
                str(comparison_path),
                "--signal-source-map",
                str(signal_map_path),
                "--driver-trace",
                str(driver_trace_path),
                "--output",
                str(divergence_graph_path),
            ]
        )
        graph = FailureDivergenceGraphReport.model_validate_json(
            divergence_graph_path.read_text(encoding="utf-8")
        )
        assert graph.schema_version == 1
        assert graph.root_identifiers == ["state", "valid"]
        assert graph.global_earliest_divergence_time == 25
        root_nodes = {node.identifier: node for node in graph.nodes if node.is_root}
        assert set(root_nodes) == {"state", "valid"}
        for node in root_nodes.values():
            assert node.mapping_status == "exact"
            assert node.driver_resolved is not True
            assert node.divergence is not None
            assert node.divergence.first_divergence_time == 25

        # 8. Evidence-bundle export over the run directory.
        run_cli(
            [
                "export-evidence",
                "--run-dir",
                str(run_dir),
                "--output-dir",
                str(evidence_bundle_dir),
                "--fail-on-failed-export",
            ]
        )
        evidence_bundle = EvidenceBundleReport.model_validate_json(
            (evidence_bundle_dir / "bundle.json").read_text(encoding="utf-8")
        )
        assert evidence_bundle.status == "passed"
        kinds = {artifact.kind for artifact in evidence_bundle.artifacts}
        assert {
            "run_metadata",
            "waveform_slice_report",
            "waveform_comparison_report",
            "signal_source_map_report",
            "rtl_driver_trace_report",
            "failure_divergence_graph_report",
            "relevant_signal_reduction_report",
        } <= kinds

    print("compact failure intelligence example check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
