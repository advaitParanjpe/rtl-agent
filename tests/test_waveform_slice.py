from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rtl_agent.waveform import (
    WaveformSliceError,
    extract_waveform_window,
    write_waveform_slice,
)

FIXTURE = Path("examples/waveforms/failure.vcd")


def write_vcd(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_parses_scopes_signals_and_bounded_window() -> None:
    report = extract_waveform_window(FIXTURE, failure_time=40, before=15, after=5)

    assert report.schema_version == 1
    assert report.source.timescale == "1ns"
    assert report.source.size_bytes == FIXTURE.stat().st_size
    assert report.source.sha256 == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()

    names = {signal.name for signal in report.selected_signals}
    assert names == {"top.clk", "top.data", "top.dut.valid", "top.dut.state"}
    data = next(signal for signal in report.selected_signals if signal.name == "top.data")
    assert data.width == 8
    assert data.kind == "vector"
    assert data.bit_range == "[7:0]"

    assert report.window.requested_start == 25
    assert report.window.requested_end == 45
    assert report.window.observed_start == 30
    assert report.window.observed_end == 40
    assert report.parse_statistics.scopes == 2
    assert report.parse_statistics.declared_variables == 4
    assert report.parse_statistics.value_changes_total == 15
    # The full waveform (t0/t10/t20/t50 events) is not copied into the slice.
    assert {change.time for change in report.value_changes} == {30, 40}


def test_initial_values_capture_pre_window_state_including_x_and_z() -> None:
    report = extract_waveform_window(FIXTURE, failure_time=40, before=15, after=5)

    initial = {item.signal: item for item in report.initial_values}
    assert initial["top.clk"].determinable is True
    assert initial["top.clk"].value == "0"
    assert initial["top.data"].value == "00000001"
    assert initial["top.dut.valid"].value == "x"
    assert initial["top.dut.state"].value == "zzzz"


def test_vector_scalar_x_and_z_values_are_represented() -> None:
    report = extract_waveform_window(FIXTURE, failure_time=50, before=0, after=0)

    by_signal = {change.signal: change.value for change in report.value_changes}
    assert by_signal["top.clk"] == "1"
    assert by_signal["top.dut.valid"] == "0"
    assert by_signal["top.dut.state"] == "xxxx"


def test_signal_filtering_by_exact_name_and_prefix() -> None:
    report = extract_waveform_window(
        FIXTURE,
        failure_time=40,
        before=40,
        after=40,
        signal_names=["top.clk", "top.missing"],
        signal_prefixes=["top.dut"],
    )

    names = {signal.name for signal in report.selected_signals}
    assert names == {"top.clk", "top.dut.valid", "top.dut.state"}
    assert "top.data" not in names
    assert "requested signal not found: top.missing" in report.warnings


def test_timestamp_boundaries_are_inclusive(tmp_path: Path) -> None:
    vcd = write_vcd(
        tmp_path / "boundary.vcd",
        "$timescale 1ns $end\n"
        "$scope module top $end\n"
        "$var wire 1 ! a $end\n"
        "$upscope $end\n"
        "$enddefinitions $end\n"
        "#0\n0!\n#10\n1!\n#20\n0!\n#30\n1!\n",
    )

    report = extract_waveform_window(vcd, failure_time=20, before=10, after=10)

    assert report.window.requested_start == 10
    assert report.window.requested_end == 30
    assert [change.time for change in report.value_changes] == [10, 20, 30]


def test_change_just_outside_window_is_excluded(tmp_path: Path) -> None:
    vcd = write_vcd(
        tmp_path / "outside.vcd",
        "$timescale 1ns $end\n"
        "$scope module top $end\n"
        "$var wire 1 ! a $end\n"
        "$upscope $end\n"
        "$enddefinitions $end\n"
        "#10\n1!\n#20\n0!\n#30\n1!\n",
    )

    report = extract_waveform_window(vcd, failure_time=20, before=9, after=9)

    assert report.window.requested_start == 11
    assert report.window.requested_end == 29
    assert [change.time for change in report.value_changes] == [20]
    # The most recent change before the window (t10) becomes the initial value.
    assert report.initial_values[0].determinable is True
    assert report.initial_values[0].value == "1"


def test_initial_value_not_determinable_when_no_prior_change(tmp_path: Path) -> None:
    vcd = write_vcd(
        tmp_path / "initial.vcd",
        "$timescale 1ns $end\n"
        "$scope module top $end\n"
        '$var wire 1 ! a $end\n$var wire 1 " b $end\n'
        "$upscope $end\n"
        "$enddefinitions $end\n"
        '#5\n1!\n#20\n1!\n1"\n',
    )

    report = extract_waveform_window(vcd, failure_time=20, before=5, after=0)

    initial = {item.signal: item for item in report.initial_values}
    assert initial["top.a"].determinable is True
    assert initial["top.a"].value == "1"
    assert initial["top.b"].determinable is False
    assert initial["top.b"].value is None


def test_window_start_is_clamped_with_warning(tmp_path: Path) -> None:
    vcd = write_vcd(
        tmp_path / "clamp.vcd",
        "$timescale 1ns $end\n"
        "$scope module top $end\n"
        "$var wire 1 ! a $end\n"
        "$upscope $end\n"
        "$enddefinitions $end\n"
        "#0\n0!\n#5\n1!\n",
    )

    report = extract_waveform_window(vcd, failure_time=5, before=100, after=0)

    assert report.window.requested_start == 0
    assert "requested window start clamped to 0" in report.warnings


def test_deterministic_serialization(tmp_path: Path) -> None:
    report = extract_waveform_window(FIXTURE, failure_time=40, before=15, after=5)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    write_waveform_slice(report, first)
    write_waveform_slice(report, second)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    assert json.loads(first.read_text(encoding="utf-8"))["schema_version"] == 1


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(WaveformSliceError, match="does not exist"):
        extract_waveform_window(tmp_path / "nope.vcd", failure_time=0, before=0, after=0)


def test_negative_failure_time_is_rejected() -> None:
    with pytest.raises(WaveformSliceError, match="failure time"):
        extract_waveform_window(FIXTURE, failure_time=-1, before=0, after=0)


def test_missing_enddefinitions_is_rejected(tmp_path: Path) -> None:
    vcd = write_vcd(
        tmp_path / "bad.vcd",
        "$timescale 1ns $end\n$scope module top $end\n$var wire 1 ! a $end\n",
    )

    with pytest.raises(WaveformSliceError, match="missing \\$enddefinitions"):
        extract_waveform_window(vcd, failure_time=0, before=0, after=0)


def test_malformed_var_width_is_rejected(tmp_path: Path) -> None:
    vcd = write_vcd(
        tmp_path / "badvar.vcd",
        "$timescale 1ns $end\n"
        "$scope module top $end\n"
        "$var wire x ! a $end\n"
        "$upscope $end\n"
        "$enddefinitions $end\n",
    )

    with pytest.raises(WaveformSliceError, match="\\$var width"):
        extract_waveform_window(vcd, failure_time=0, before=0, after=0)


def test_malformed_timestamp_is_rejected(tmp_path: Path) -> None:
    vcd = write_vcd(
        tmp_path / "badtime.vcd",
        "$timescale 1ns $end\n"
        "$scope module top $end\n"
        "$var wire 1 ! a $end\n"
        "$upscope $end\n"
        "$enddefinitions $end\n"
        "#oops\n1!\n",
    )

    with pytest.raises(WaveformSliceError, match="timestamp"):
        extract_waveform_window(vcd, failure_time=0, before=0, after=0)


def test_unsafe_directory_output_is_rejected(tmp_path: Path) -> None:
    report = extract_waveform_window(FIXTURE, failure_time=40, before=15, after=5)
    directory = tmp_path / "out-dir"
    directory.mkdir()

    with pytest.raises(WaveformSliceError, match="directory"):
        write_waveform_slice(report, directory)


def test_missing_timescale_produces_warning(tmp_path: Path) -> None:
    vcd = write_vcd(
        tmp_path / "no-timescale.vcd",
        "$scope module top $end\n"
        "$var wire 1 ! a $end\n"
        "$upscope $end\n"
        "$enddefinitions $end\n"
        "#0\n0!\n",
    )

    report = extract_waveform_window(vcd, failure_time=0, before=0, after=0)

    assert report.source.timescale is None
    assert "timescale not found in VCD header" in report.warnings
