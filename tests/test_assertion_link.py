from __future__ import annotations

import json
from pathlib import Path

import pytest

from rtl_agent.assertion_link import (
    AssertionLinkError,
    link_assertion_to_waveform,
    write_link_report,
)
from rtl_agent.models import CommandStatus
from rtl_agent.triage_models import (
    AssertionFailure,
    TriageReport,
    TriageSource,
    WaveformReference,
)

FIXTURE_VCD = Path("examples/waveforms/failure.vcd").resolve()


def write_vcd(path: Path, timescale: str) -> Path:
    path.write_text(
        f"$timescale {timescale} $end\n"
        "$scope module top $end\n"
        "$var wire 1 ! clk $end\n"
        "$upscope $end\n"
        "$enddefinitions $end\n"
        "#0\n0!\n#40\n1!\n#80\n0!\n",
        encoding="utf-8",
    )
    return path


def make_triage(
    tmp_path: Path,
    *,
    assertions: list[AssertionFailure],
    waveforms: list[WaveformReference],
) -> Path:
    triage = TriageReport(
        command_name="sim",
        command_status=str(CommandStatus.FAILED),
        command_exit_code=1,
        command_result_path=tmp_path / "result.json",
        stdout_path=tmp_path / "stdout.log",
        stderr_path=tmp_path / "stderr.log",
        assertion_failures=assertions,
        waveform_references=waveforms,
    )
    path = tmp_path / "triage.json"
    path.write_text(json.dumps(triage.model_dump(mode="json")), encoding="utf-8")
    return path


def assertion(time_context: str | None, line: int = 10) -> AssertionFailure:
    return AssertionFailure(
        source=TriageSource.STDERR,
        line=line,
        summary=f"ASSERTION FAILED p at time {time_context}",
        signal_or_label="p",
        time_context=time_context,
    )


def waveform_ref(path: str, resolved: Path | None, exists: bool = True) -> WaveformReference:
    return WaveformReference(
        source=TriageSource.STDOUT,
        line=3,
        path=path,
        exists=exists,
        resolved_path=resolved,
        evidence=f"dumped {path}",
    )


def test_successful_linking_generates_bounded_slice(tmp_path: Path) -> None:
    triage_path = make_triage(
        tmp_path,
        assertions=[assertion("40 ns")],
        waveforms=[waveform_ref("failure.vcd", FIXTURE_VCD)],
    )
    slice_output = tmp_path / "slice.json"

    report = link_assertion_to_waveform(
        triage_path,
        slice_output,
        assertion_index=0,
        before=15,
        after=5,
        signal_prefixes=["top.dut"],
    )

    assert report.schema_version == 1
    assert report.selected_assertion.assertion_id == "assertion-0"
    assert report.timestamp_conversion.failure_timestamp_ticks == 40
    assert report.timestamp_conversion.exact is True
    assert report.selected_waveform.resolved_path == FIXTURE_VCD
    assert slice_output.exists()
    assert report.slice_selected_signal_count == 2
    assert report.warnings == []
    assert report.unresolved_ambiguities == []


def test_selection_by_stable_id_matches_index(tmp_path: Path) -> None:
    triage_path = make_triage(
        tmp_path,
        assertions=[assertion("40 ns")],
        waveforms=[waveform_ref("failure.vcd", FIXTURE_VCD)],
    )

    report = link_assertion_to_waveform(
        triage_path, tmp_path / "slice.json", assertion_id="assertion-0"
    )

    assert report.selected_assertion.index == 0


def test_timescale_conversion_scales_ticks(tmp_path: Path) -> None:
    vcd = write_vcd(tmp_path / "ps.vcd", "10 ps")
    triage_path = make_triage(
        tmp_path,
        assertions=[assertion("40 ns")],
        waveforms=[waveform_ref("ps.vcd", vcd)],
    )

    report = link_assertion_to_waveform(triage_path, tmp_path / "slice.json", assertion_index=0)

    # 40 ns / 10 ps = 4000 ticks.
    assert report.timestamp_conversion.failure_timestamp_ticks == 4000
    assert report.timestamp_conversion.vcd_tick_femtoseconds == 10_000
    assert report.timestamp_conversion.exact is True


def test_non_integer_conversion_is_floored_with_warning(tmp_path: Path) -> None:
    vcd = write_vcd(tmp_path / "ns.vcd", "1 ns")
    triage_path = make_triage(
        tmp_path,
        assertions=[assertion("40.5 ns")],
        waveforms=[waveform_ref("ns.vcd", vcd)],
    )

    report = link_assertion_to_waveform(triage_path, tmp_path / "slice.json", assertion_index=0)

    assert report.timestamp_conversion.failure_timestamp_ticks == 40
    assert report.timestamp_conversion.exact is False
    assert any("exact VCD tick" in warning for warning in report.warnings)


def test_no_assertion_selected_is_rejected(tmp_path: Path) -> None:
    triage_path = make_triage(
        tmp_path,
        assertions=[assertion("40 ns")],
        waveforms=[waveform_ref("failure.vcd", FIXTURE_VCD)],
    )

    with pytest.raises(AssertionLinkError, match="no assertion selected"):
        link_assertion_to_waveform(triage_path, tmp_path / "slice.json")


def test_missing_timestamp_is_rejected(tmp_path: Path) -> None:
    triage_path = make_triage(
        tmp_path,
        assertions=[assertion(None)],
        waveforms=[waveform_ref("failure.vcd", FIXTURE_VCD)],
    )

    with pytest.raises(AssertionLinkError, match="no usable timestamp"):
        link_assertion_to_waveform(triage_path, tmp_path / "slice.json", assertion_index=0)


def test_ambiguous_time_unit_is_rejected(tmp_path: Path) -> None:
    triage_path = make_triage(
        tmp_path,
        assertions=[assertion("5 cycles")],
        waveforms=[waveform_ref("failure.vcd", FIXTURE_VCD)],
    )

    with pytest.raises(AssertionLinkError, match="ambiguous"):
        link_assertion_to_waveform(triage_path, tmp_path / "slice.json", assertion_index=0)


def test_missing_vcd_timescale_is_rejected(tmp_path: Path) -> None:
    vcd = tmp_path / "no-ts.vcd"
    vcd.write_text(
        "$scope module top $end\n"
        "$var wire 1 ! clk $end\n"
        "$upscope $end\n"
        "$enddefinitions $end\n"
        "#40\n1!\n",
        encoding="utf-8",
    )
    triage_path = make_triage(
        tmp_path,
        assertions=[assertion("40 ns")],
        waveforms=[waveform_ref("no-ts.vcd", vcd)],
    )

    with pytest.raises(AssertionLinkError, match="no \\$timescale"):
        link_assertion_to_waveform(triage_path, tmp_path / "slice.json", assertion_index=0)


def test_multiple_waveforms_require_disambiguation(tmp_path: Path) -> None:
    other = write_vcd(tmp_path / "other.vcd", "1 ns")
    triage_path = make_triage(
        tmp_path,
        assertions=[assertion("40 ns")],
        waveforms=[
            waveform_ref("failure.vcd", FIXTURE_VCD),
            waveform_ref("other.vcd", other),
        ],
    )

    with pytest.raises(AssertionLinkError, match="multiple candidate"):
        link_assertion_to_waveform(triage_path, tmp_path / "slice.json", assertion_index=0)


def test_waveform_path_disambiguation_records_others(tmp_path: Path) -> None:
    other = write_vcd(tmp_path / "other.vcd", "1 ns")
    triage_path = make_triage(
        tmp_path,
        assertions=[assertion("40 ns")],
        waveforms=[
            waveform_ref("failure.vcd", FIXTURE_VCD),
            waveform_ref("other.vcd", other),
        ],
    )

    report = link_assertion_to_waveform(
        triage_path,
        tmp_path / "slice.json",
        assertion_index=0,
        waveform_path=other,
    )

    assert report.selected_waveform.resolved_path == other.resolve()
    assert any("not selected" in note for note in report.unresolved_ambiguities)


def test_missing_waveform_file_is_rejected(tmp_path: Path) -> None:
    triage_path = make_triage(
        tmp_path,
        assertions=[assertion("40 ns")],
        waveforms=[waveform_ref("gone.vcd", tmp_path / "gone.vcd", exists=False)],
    )

    with pytest.raises(AssertionLinkError, match="missing on disk"):
        link_assertion_to_waveform(triage_path, tmp_path / "slice.json", assertion_index=0)


def test_unsupported_format_is_rejected(tmp_path: Path) -> None:
    triage_path = make_triage(
        tmp_path,
        assertions=[assertion("40 ns")],
        waveforms=[waveform_ref("dump.fst", tmp_path / "dump.fst")],
    )

    with pytest.raises(AssertionLinkError, match="unsupported formats"):
        link_assertion_to_waveform(triage_path, tmp_path / "slice.json", assertion_index=0)


def test_malformed_waveform_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad.vcd"
    bad.write_text("$timescale 1 ns $end\n$var wire 1 ! clk $end\n", encoding="utf-8")
    triage_path = make_triage(
        tmp_path,
        assertions=[assertion("40 ns")],
        waveforms=[waveform_ref("bad.vcd", bad)],
    )

    with pytest.raises(AssertionLinkError, match="missing or malformed"):
        link_assertion_to_waveform(triage_path, tmp_path / "slice.json", assertion_index=0)


def test_deterministic_output(tmp_path: Path) -> None:
    triage_path = make_triage(
        tmp_path,
        assertions=[assertion("40 ns")],
        waveforms=[waveform_ref("failure.vcd", FIXTURE_VCD)],
    )
    report = link_assertion_to_waveform(
        triage_path, tmp_path / "slice.json", assertion_index=0, before=15, after=5
    )
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    write_link_report(report, first)
    write_link_report(report, second)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    assert json.loads(first.read_text(encoding="utf-8"))["schema_version"] == 1


def test_rejects_malformed_triage_report(tmp_path: Path) -> None:
    bad = tmp_path / "triage.json"
    bad.write_text("{}", encoding="utf-8")

    with pytest.raises(AssertionLinkError, match="could not load triage report"):
        link_assertion_to_waveform(bad, tmp_path / "slice.json", assertion_index=0)


def test_checked_in_fixture_links_from_repo_root(tmp_path: Path) -> None:
    report = link_assertion_to_waveform(
        Path("examples/waveforms/triage-report.json"),
        tmp_path / "slice.json",
        assertion_id="assertion-0",
        before=15,
        after=5,
    )

    assert report.timestamp_conversion.failure_timestamp_ticks == 40
    assert report.selected_waveform.path == "examples/waveforms/failure.vcd"
    assert report.selected_waveform.resolved_path == FIXTURE_VCD
