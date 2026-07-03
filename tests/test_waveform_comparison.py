from __future__ import annotations

import json
from pathlib import Path

import pytest

from rtl_agent.waveform import write_waveform_slice
from rtl_agent.waveform_comparison import (
    WaveformComparisonError,
    compare_waveforms,
    write_comparison_report,
)
from rtl_agent.waveform_slice_models import (
    WaveformInitialValue,
    WaveformParseStatistics,
    WaveformSignal,
    WaveformSliceReport,
    WaveformSourceMetadata,
    WaveformValueChange,
    WaveformValueKind,
    WaveformWindow,
)


def make_slice(
    tmp_path: Path,
    filename: str,
    signals: list[tuple[str, str]],
    changes: list[tuple[int, str, str, str]],
    initials: list[tuple[str, str, str | None]] | None = None,
    timescale: str | None = "1ns",
    start: int = 25,
    end: int = 55,
) -> Path:
    report = WaveformSliceReport(
        source=WaveformSourceMetadata(
            path=tmp_path / f"{filename}.vcd", size_bytes=1, sha256="0" * 64, timescale=timescale
        ),
        window=WaveformWindow(
            failure_time=start,
            before=0,
            after=end - start,
            requested_start=start,
            requested_end=end,
        ),
        selected_signals=[
            WaveformSignal(
                name=name, identifier=ident, var_type="wire", width=1, kind=WaveformValueKind.SCALAR
            )
            for name, ident in signals
        ],
        initial_values=[
            WaveformInitialValue(
                signal=name, identifier=ident, determinable=value is not None, value=value
            )
            for name, ident, value in (initials or [])
        ],
        value_changes=[
            WaveformValueChange(time=time, signal=name, identifier=ident, value=value)
            for time, name, ident, value in changes
        ],
        parse_statistics=WaveformParseStatistics(
            scopes=1,
            declared_variables=len(signals),
            selected_signals=len(signals),
            timestamps_total=0,
            value_changes_total=len(changes),
            value_changes_in_window=len(changes),
        ),
    )
    path = tmp_path / f"{filename}.json"
    write_waveform_slice(report, path)
    return path


def test_identical_timelines_report_no_divergence(tmp_path: Path) -> None:
    signals: list[tuple[str, str]] = [("top.a", "!")]
    changes: list[tuple[int, str, str, str]] = [(30, "top.a", "!", "1")]
    initials: list[tuple[str, str, str | None]] = [("top.a", "!", "0")]
    failing = make_slice(tmp_path, "fail", signals, changes, initials)
    passing = make_slice(tmp_path, "pass", signals, changes, initials)

    report = compare_waveforms(failing, passing)

    assert report.diverging_signals == []
    assert report.identical_signals == ["top.a"]
    assert report.global_earliest_divergence_time is None
    assert report.time_basis.kind == "shared_ticks"


def test_first_divergence_time_and_values(tmp_path: Path) -> None:
    failing = make_slice(
        tmp_path,
        "fail",
        [("top.a", "!")],
        [(30, "top.a", "!", "1"), (40, "top.a", "!", "0")],
        [("top.a", "!", "0")],
    )
    passing = make_slice(
        tmp_path,
        "pass",
        [("top.a", "!")],
        [(30, "top.a", "!", "1")],
        [("top.a", "!", "0")],
    )

    report = compare_waveforms(failing, passing)

    assert len(report.diverging_signals) == 1
    signal = report.diverging_signals[0]
    assert signal.name == "top.a"
    assert signal.first_divergence_time == 40
    assert signal.failing_value_at_divergence == "0"
    assert signal.passing_value_at_divergence == "1"
    assert signal.failing_transition_count == 2
    assert signal.passing_transition_count == 1
    assert report.global_earliest_divergence_time == 40
    assert report.global_earliest_divergence_signals == ["top.a"]


def test_divergence_duration_and_intervals(tmp_path: Path) -> None:
    # Failing differs from passing on [25,30) and again on [50,55).
    failing = make_slice(
        tmp_path,
        "fail",
        [("top.s", "!")],
        [(30, "top.s", "!", "0"), (50, "top.s", "!", "1")],
        [("top.s", "!", "1")],
    )
    passing = make_slice(
        tmp_path,
        "pass",
        [("top.s", "!")],
        [(30, "top.s", "!", "0"), (50, "top.s", "!", "0")],
        [("top.s", "!", "0")],
    )

    report = compare_waveforms(failing, passing)

    signal = report.diverging_signals[0]
    assert signal.divergence_duration == 10
    assert [(iv.start, iv.end) for iv in signal.divergence_intervals] == [(25, 30), (50, 55)]


def test_xz_difference_detected(tmp_path: Path) -> None:
    failing = make_slice(tmp_path, "fail", [("top.a", "!")], [], [("top.a", "!", "x")])
    passing = make_slice(tmp_path, "pass", [("top.a", "!")], [], [("top.a", "!", "0")])

    report = compare_waveforms(failing, passing)

    signal = report.diverging_signals[0]
    assert signal.xz_difference is True
    assert signal.failing_value_at_divergence == "x"
    assert signal.passing_value_at_divergence == "0"


def test_added_and_removed_signals(tmp_path: Path) -> None:
    failing = make_slice(
        tmp_path, "fail", [("top.a", "!"), ("top.new", "#")], [], [("top.a", "!", "0")]
    )
    passing = make_slice(
        tmp_path, "pass", [("top.a", "!"), ("top.old", "$")], [], [("top.a", "!", "0")]
    )

    report = compare_waveforms(failing, passing)

    assert report.added_signals == ["top.new"]
    assert report.removed_signals == ["top.old"]
    assert report.shared_signal_count == 1


def test_ranking_orders_most_divergent_first(tmp_path: Path) -> None:
    failing = make_slice(
        tmp_path,
        "fail",
        [("top.long", "!"), ("top.short", '"')],
        [(50, "top.short", '"', "1")],
        [("top.long", "!", "1"), ("top.short", '"', "0")],
    )
    passing = make_slice(
        tmp_path,
        "pass",
        [("top.long", "!"), ("top.short", '"')],
        [(50, "top.short", '"', "0")],
        [("top.long", "!", "0"), ("top.short", '"', "0")],
    )

    report = compare_waveforms(failing, passing)

    names = [signal.name for signal in report.diverging_signals]
    assert names[0] == "top.long"  # diverges across the whole window
    assert (
        report.diverging_signals[0].divergence_score > report.diverging_signals[1].divergence_score
    )


def test_incompatible_timescales_are_normalized_explicitly(tmp_path: Path) -> None:
    failing = make_slice(
        tmp_path, "fail", [("top.a", "!")], [], [("top.a", "!", "0")], timescale="1ns"
    )
    passing = make_slice(
        tmp_path,
        "pass",
        [("top.a", "!")],
        [],
        [("top.a", "!", "0")],
        timescale="10ps",
        start=2500,
        end=5500,
    )

    report = compare_waveforms(failing, passing)

    assert report.time_basis.kind == "normalized_femtoseconds"
    assert report.time_basis.normalized is True
    assert report.time_basis.failing_tick_femtoseconds == 1_000_000
    assert report.time_basis.passing_tick_femtoseconds == 10_000
    assert report.time_basis.common_start == 25_000_000
    assert report.time_basis.common_end == 55_000_000
    assert any("normalized to femtoseconds" in warning for warning in report.warnings)


def test_unparseable_timescale_is_not_silently_aligned(tmp_path: Path) -> None:
    failing = make_slice(
        tmp_path, "fail", [("top.a", "!")], [], [("top.a", "!", "0")], timescale=None
    )
    passing = make_slice(
        tmp_path, "pass", [("top.a", "!")], [], [("top.a", "!", "0")], timescale="1ns"
    )

    report = compare_waveforms(failing, passing)

    assert report.time_basis.kind == "unnormalized_ticks"
    assert report.time_basis.normalized is False
    assert any("without normalization" in warning for warning in report.warnings)


def test_window_mismatch_uses_overlap_and_warns(tmp_path: Path) -> None:
    failing = make_slice(
        tmp_path, "fail", [("top.a", "!")], [], [("top.a", "!", "0")], start=20, end=50
    )
    passing = make_slice(
        tmp_path, "pass", [("top.a", "!")], [], [("top.a", "!", "0")], start=25, end=55
    )

    report = compare_waveforms(failing, passing)

    assert report.time_basis.common_start == 25
    assert report.time_basis.common_end == 50
    assert any("window mismatch" in warning for warning in report.warnings)


def test_no_overlapping_window_skips_comparison(tmp_path: Path) -> None:
    failing = make_slice(
        tmp_path, "fail", [("top.a", "!")], [], [("top.a", "!", "0")], start=0, end=10
    )
    passing = make_slice(
        tmp_path, "pass", [("top.a", "!")], [], [("top.a", "!", "1")], start=20, end=30
    )

    report = compare_waveforms(failing, passing)

    assert report.diverging_signals == []
    assert any("no overlapping time window" in warning for warning in report.warnings)


def test_ambiguous_duplicate_name_is_flagged(tmp_path: Path) -> None:
    failing = make_slice(
        tmp_path,
        "fail",
        [("top.a", "!"), ("top.a", "#")],
        [],
        [("top.a", "!", "0")],
    )
    passing = make_slice(tmp_path, "pass", [("top.a", "!")], [], [("top.a", "!", "0")])

    report = compare_waveforms(failing, passing)

    assert any("ambiguous signal matching" in warning for warning in report.warnings)
    assert report.diverging_signals == []
    assert report.identical_signals == []


def test_no_shared_signals_warns(tmp_path: Path) -> None:
    failing = make_slice(tmp_path, "fail", [("top.a", "!")], [], [("top.a", "!", "0")])
    passing = make_slice(tmp_path, "pass", [("top.b", '"')], [], [("top.b", '"', "0")])

    report = compare_waveforms(failing, passing)

    assert any("no shared signals" in warning for warning in report.warnings)


def test_deterministic_output(tmp_path: Path) -> None:
    failing = make_slice(
        tmp_path,
        "fail",
        [("top.a", "!")],
        [(40, "top.a", "!", "0")],
        [("top.a", "!", "1")],
    )
    passing = make_slice(tmp_path, "pass", [("top.a", "!")], [], [("top.a", "!", "1")])

    report = compare_waveforms(failing, passing)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_comparison_report(report, first)
    write_comparison_report(report, second)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    assert json.loads(first.read_text(encoding="utf-8"))["schema_version"] == 1


def test_malformed_slice_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    good = make_slice(tmp_path, "good", [("top.a", "!")], [], [("top.a", "!", "0")])

    with pytest.raises(WaveformComparisonError, match="could not load failing waveform slice"):
        compare_waveforms(bad, good)
