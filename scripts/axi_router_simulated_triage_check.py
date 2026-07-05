"""Integrate real simulator logs and assertion evidence into failure intelligence.

This pilot wires the existing services end to end over a genuinely failing
simulation, without adding a parallel pipeline. Using Icarus Verilog it runs a
deterministic failing simulation whose testbench emits a stable, timestamped
assertion-failure marker and dumps a VCD; the run is executed through the
existing command runner (so its real logs and non-zero terminal status are
captured), triaged with the existing triage service (which recovers the
assertion timestamp and the referenced waveform), and linked to the generated
waveform with the existing assertion-to-waveform linker (which derives the
failure timestamp and the VCD path — the user provides neither). The derived
failing waveform and timestamp then drive the existing failure-intelligence
orchestration, inspection, and portable-package export.

The simulator is a gated fixture-generation/dev dependency: when ``iverilog`` and
``vvp`` are unavailable the check skips cleanly and returns success, so the
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

from rtl_agent.assertion_waveform_link_models import AssertionWaveformLinkReport
from rtl_agent.failure_report_models import FailureReport
from rtl_agent.signal_source_map_models import SignalSourceMapReport
from rtl_agent.triage_models import TriageReport
from rtl_agent.waveform_comparison_models import WaveformComparisonReport

SIM = ROOT / "examples" / "axi-router-sim-triage"
RTL_DIR = SIM / "rtl"
DESIGN = RTL_DIR / "axi_pipe.sv"
TESTBENCH = SIM / "tb" / "axi_pipe_tb.sv"
FIXTURE_CONFIG = ROOT / "examples" / "axi-router-sim-triage-agent.yaml"

DESIGN_FILE = "axi_pipe.sv"
EXPECTED_FAILURE_TIME = 45
DIVERGENT_SIGNAL = "axi_pipe_tb.axi_pipe.payload_out"
DIVERGENT_LEAF = "payload_out"


def main() -> int:
    iverilog = shutil.which("iverilog")
    vvp = shutil.which("vvp")
    if iverilog is None or vvp is None:
        print("axi router simulated triage check skipped (iverilog/vvp not available)")
        return 0

    with tempfile.TemporaryDirectory(prefix="rtl-agent-axi-triage-") as raw_tmp:
        workspace = Path(raw_tmp)
        # Fixture prep: compile both builds; generate the passing reference VCD
        # directly (the failing run is executed through the command runner).
        passing_binary = _compile(iverilog, workspace, "pass", inject_fault=False)
        failing_binary = _compile(iverilog, workspace, "fail", inject_fault=True)
        passing_vcd = workspace / "passing.vcd"
        _run([vvp, str(passing_binary), f"+vcd={passing_vcd}"], workspace)
        assert passing_vcd.exists()

        result_path = _run_failing_simulation(workspace, vvp, failing_binary)
        triage_path = _triage(workspace, result_path)
        link_report = _link(workspace, triage_path)

        failing_vcd = Path(link_report.selected_waveform.resolved_path)
        failure_time = link_report.timestamp_conversion.failure_timestamp_ticks
        assert failure_time == EXPECTED_FAILURE_TIME
        assert link_report.timestamp_conversion.exact is True

        run_dir = _run_failure_intelligence(workspace, failing_vcd, passing_vcd, failure_time)
        _check_localization(run_dir, failure_time)
        _check_consistency(link_report, triage_path, run_dir)
        _check_inspection_and_package(run_dir, workspace)

    print("axi router simulated triage check passed")
    return 0


def _compile(iverilog: str, workspace: Path, label: str, *, inject_fault: bool) -> Path:
    binary = workspace / f"{label}.vvp"
    args = [iverilog, "-g2012", "-o", str(binary)]
    if inject_fault:
        args.append("-DINJECT_FAULT")
    args.extend([str(DESIGN), str(TESTBENCH)])
    _run(args, workspace)
    return binary


def _run_failing_simulation(workspace: Path, vvp: str, failing_binary: Path) -> Path:
    """Execute the failing simulation through the existing command runner."""

    failing_vcd = workspace / "cmd_failure.vcd"
    config = workspace / "sim-config.yaml"
    config.write_text(
        "\n".join(
            [
                "schema_version: 1",
                f"repository_path: {RTL_DIR}",
                "run_artifact_dir: runs",
                "allowed_working_paths:",
                "  - .",
                "execution:",
                "  timeout_seconds: 120",
                "commands:",
                "  sim-failing:",
                "    argv:",
                f"      - {vvp}",
                f"      - {failing_binary}",
                f"      - +vcd={failing_vcd}",
                "    cwd: .",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    # The failing simulation exits non-zero; the runner records it as failed.
    summary = run_cli(
        ["run-command", "--config", str(config), "--command", "sim-failing"],
        expected_exit=1,
    )
    assert summary["status"] == "failed"
    assert summary["exit_code"] == 1
    assert failing_vcd.exists()
    return Path(summary["result_path"])


def _triage(workspace: Path, result_path: Path) -> Path:
    triage_path = workspace / "triage.json"
    run_cli(["triage-command", "--command-result", str(result_path), "--output", str(triage_path)])
    triage = TriageReport.model_validate_json(triage_path.read_text(encoding="utf-8"))
    # The failing run was captured with its assertion marker and waveform.
    assert triage.command_status == "failed"
    assert triage.assertion_failures, "no assertion failure recovered from the simulation log"
    assertion = triage.assertion_failures[0]
    assert assertion.signal_or_label == "payload_stable"
    assert assertion.time_context is not None and "45" in assertion.time_context
    assert any(
        reference.path.endswith("cmd_failure.vcd") for reference in triage.waveform_references
    )
    assert all(
        reference.exists
        for reference in triage.waveform_references
        if reference.path.endswith(".vcd")
    )
    return triage_path


def _link(workspace: Path, triage_path: Path) -> AssertionWaveformLinkReport:
    link_path = workspace / "link.json"
    slice_path = workspace / "failing-slice.json"
    # Select the finding; the failure timestamp and VCD path are derived, not
    # provided by the user.
    run_cli(
        [
            "link-assertion-waveform",
            "--triage-report",
            str(triage_path),
            "--output",
            str(link_path),
            "--slice-output",
            str(slice_path),
            "--assertion-index",
            "0",
            "--before",
            "20",
            "--after",
            "20",
        ]
    )
    return AssertionWaveformLinkReport.model_validate_json(link_path.read_text(encoding="utf-8"))


def _run_failure_intelligence(
    workspace: Path, failing_vcd: Path, passing_vcd: Path, failure_time: int
) -> Path:
    run_root = workspace / ".rtl-agent" / "runs"
    run_id = "axi-router-sim-triage-pilot"
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
            str(FIXTURE_CONFIG),
            "--failure-time",
            str(failure_time),
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
    return run_root / run_id


def _check_localization(run_dir: Path, failure_time: int) -> None:
    comparison = WaveformComparisonReport.model_validate_json(
        (run_dir / "waveform" / "comparison.json").read_text(encoding="utf-8")
    )
    # The localized earliest divergence agrees with the assertion timestamp.
    assert comparison.global_earliest_divergence_time == failure_time
    diverging = {signal.name for signal in comparison.diverging_signals}
    assert DIVERGENT_SIGNAL in diverging

    signal_map = SignalSourceMapReport.model_validate_json(
        (run_dir / "signal-source-map.json").read_text(encoding="utf-8")
    )
    mapping = next(m for m in signal_map.mappings if m.signal == DIVERGENT_SIGNAL)
    assert mapping.status == "exact"
    assert {candidate.file_path for candidate in mapping.candidates} == {DESIGN_FILE}

    report = FailureReport.model_validate_json(
        (run_dir / "failure-report.json").read_text(encoding="utf-8")
    )
    assert report.earliest_divergence_time == failure_time
    assert DIVERGENT_LEAF in report.earliest_divergence_signals
    assert {location.file_path for location in report.candidate_source_locations} == {DESIGN_FILE}
    assert "never identifies a root cause" in " ".join(report.parser_notes).lower()


def _check_consistency(
    link_report: AssertionWaveformLinkReport, triage_path: Path, run_dir: Path
) -> None:
    """The triaged failure and the localized divergence describe one run."""

    triage = TriageReport.model_validate_json(triage_path.read_text(encoding="utf-8"))
    linked_vcd = Path(link_report.selected_waveform.resolved_path).name
    assert linked_vcd == "cmd_failure.vcd"
    assert any(reference.path.endswith(linked_vcd) for reference in triage.waveform_references)
    # The failure-intelligence run consumed the same failing waveform the triage
    # linked, and its earliest divergence equals the derived assertion time.
    manifest = (run_dir / "run-manifest.json").read_text(encoding="utf-8")
    assert linked_vcd in manifest
    comparison = WaveformComparisonReport.model_validate_json(
        (run_dir / "waveform" / "comparison.json").read_text(encoding="utf-8")
    )
    assert (
        comparison.global_earliest_divergence_time
        == link_report.timestamp_conversion.failure_timestamp_ticks
    )


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


if __name__ == "__main__":
    sys.exit(main())
