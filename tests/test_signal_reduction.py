from __future__ import annotations

import json
from pathlib import Path

import pytest

from rtl_agent.assertion_link import link_assertion_to_waveform, write_link_report
from rtl_agent.signal_reduction import (
    SignalReductionError,
    reduce_relevant_signals,
    write_reduction_report,
)
from rtl_agent.waveform import write_waveform_slice
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


def sig(
    name: str, ident: str, width: int = 1, kind: WaveformValueKind = WaveformValueKind.SCALAR
) -> WaveformSignal:
    return WaveformSignal(name=name, identifier=ident, var_type="wire", width=width, kind=kind)


def vc(time: int, name: str, ident: str, value: str) -> WaveformValueChange:
    return WaveformValueChange(time=time, signal=name, identifier=ident, value=value)


def iv(name: str, ident: str, value: str | None) -> WaveformInitialValue:
    return WaveformInitialValue(
        signal=name, identifier=ident, determinable=value is not None, value=value
    )


def make_slice(
    tmp_path: Path,
    signals: list[WaveformSignal],
    value_changes: list[WaveformValueChange],
    initial_values: list[WaveformInitialValue] | None = None,
    failure_time: int = 40,
    before: int = 15,
    after: int = 5,
    name: str = "slice.json",
) -> Path:
    report = WaveformSliceReport(
        source=WaveformSourceMetadata(
            path=tmp_path / "x.vcd", size_bytes=1, sha256="0" * 64, timescale="1ns"
        ),
        window=WaveformWindow(
            failure_time=failure_time,
            before=before,
            after=after,
            requested_start=failure_time - before,
            requested_end=failure_time + after,
        ),
        selected_signals=signals,
        initial_values=initial_values or [],
        value_changes=value_changes,
        parse_statistics=WaveformParseStatistics(
            scopes=1,
            declared_variables=len(signals),
            selected_signals=len(signals),
            timestamps_total=0,
            value_changes_total=len(value_changes),
            value_changes_in_window=len(value_changes),
        ),
    )
    path = tmp_path / name
    write_waveform_slice(report, path)
    return path


def test_assertion_named_signal_ranks_highest(tmp_path: Path) -> None:
    slice_path = make_slice(
        tmp_path,
        [sig("top.a", "!"), sig("top.b", '"')],
        [vc(30, "top.a", "!", "1"), vc(30, "top.b", '"', "0")],
    )

    report = reduce_relevant_signals(
        slice_path, tmp_path / "reduced.json", assertion_signal="top.a"
    )

    assert report.retained_signals[0].name == "top.a"
    criteria = {reason.criterion for reason in report.retained_signals[0].reasons}
    assert "assertion_named" in criteria
    assert report.retained_signals[0].score > report.retained_signals[1].score


def test_transition_at_failure_scores_above_plain_transition(tmp_path: Path) -> None:
    slice_path = make_slice(
        tmp_path,
        [sig("top.a", "!"), sig("top.b", '"')],
        [vc(40, "top.a", "!", "1"), vc(30, "top.b", '"', "0")],
    )

    report = reduce_relevant_signals(slice_path, tmp_path / "reduced.json")

    ranked = {signal.name: signal for signal in report.retained_signals}
    assert ranked["top.a"].score > ranked["top.b"].score
    assert "transition_at_failure" in {r.criterion for r in ranked["top.a"].reasons}


def test_unknown_or_highz_signal_is_retained(tmp_path: Path) -> None:
    # A signal with only an x initial value and no in-window transition.
    slice_path = make_slice(
        tmp_path,
        [sig("top.q", "!")],
        [],
        initial_values=[iv("top.q", "!", "x")],
    )

    report = reduce_relevant_signals(slice_path, tmp_path / "reduced.json")

    assert [s.name for s in report.retained_signals] == ["top.q"]
    assert {r.criterion for r in report.retained_signals[0].reasons} == {"unknown_or_highz"}


def test_hierarchy_proximity_and_exclusion(tmp_path: Path) -> None:
    slice_path = make_slice(
        tmp_path,
        [sig("top.dut.state", "!"), sig("top.other", '"')],
        [],
    )

    report = reduce_relevant_signals(
        slice_path, tmp_path / "reduced.json", assertion_signal="top.dut.valid"
    )

    retained = {s.name for s in report.retained_signals}
    assert retained == {"top.dut.state"}
    assert "hierarchy_proximity" in {r.criterion for r in report.retained_signals[0].reasons}
    excluded_names = {name for summary in report.excluded for name in summary.signals}
    assert "top.other" in excluded_names


def test_no_matching_evidence_yields_empty_with_warning(tmp_path: Path) -> None:
    slice_path = make_slice(tmp_path, [sig("top.idle", "!")], [])

    report = reduce_relevant_signals(slice_path, tmp_path / "reduced.json")

    assert report.retained_signals == []
    assert any("no signals matched" in warning for warning in report.warnings)
    reduced = json.loads((tmp_path / "reduced.json").read_text(encoding="utf-8"))
    assert reduced["selected_signals"] == []


def test_empty_slice_warns(tmp_path: Path) -> None:
    slice_path = make_slice(tmp_path, [], [])

    report = reduce_relevant_signals(slice_path, tmp_path / "reduced.json")

    assert any("contains no signals" in warning for warning in report.warnings)


def test_max_signals_cap_drops_lower_scores(tmp_path: Path) -> None:
    slice_path = make_slice(
        tmp_path,
        [sig("top.a", "!"), sig("top.b", '"'), sig("top.c", "#")],
        [vc(40, "top.a", "!", "1"), vc(30, "top.b", '"', "0"), vc(30, "top.c", "#", "0")],
    )

    report = reduce_relevant_signals(slice_path, tmp_path / "reduced.json", max_signals=1)

    assert len(report.retained_signals) == 1
    assert report.retained_signals[0].name == "top.a"
    assert any("capped at max-signals" in warning for warning in report.warnings)
    dropped = {name for summary in report.excluded for name in summary.signals}
    assert {"top.b", "top.c"} <= dropped


def test_reduced_slice_is_strict_subset(tmp_path: Path) -> None:
    slice_path = make_slice(
        tmp_path,
        [sig("top.a", "!"), sig("top.idle", '"')],
        [vc(40, "top.a", "!", "1")],
    )

    report = reduce_relevant_signals(slice_path, tmp_path / "reduced.json")

    reduced = json.loads((tmp_path / "reduced.json").read_text(encoding="utf-8"))
    names = {s["name"] for s in reduced["selected_signals"]}
    assert names == {"top.a"}
    assert all(change["signal"] == "top.a" for change in reduced["value_changes"])
    assert report.reduced_slice_sha256


def test_deterministic_output(tmp_path: Path) -> None:
    slice_path = make_slice(
        tmp_path,
        [sig("top.a", "!"), sig("top.b", '"')],
        [vc(40, "top.a", "!", "1"), vc(30, "top.b", '"', "0")],
    )

    report_one = reduce_relevant_signals(slice_path, tmp_path / "r1.json")
    report_two = reduce_relevant_signals(slice_path, tmp_path / "r2.json")
    assert (tmp_path / "r1.json").read_text() == (tmp_path / "r2.json").read_text()

    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_reduction_report(report_one, first)
    write_reduction_report(report_two, second)
    # Reports differ only by the reduced-slice output path; the retained ranking is identical.
    assert [s.name for s in report_one.retained_signals] == [
        s.name for s in report_two.retained_signals
    ]
    assert json.loads(first.read_text())["schema_version"] == 1


def test_assertion_link_context_is_used(tmp_path: Path) -> None:
    link = link_assertion_to_waveform(
        Path("examples/waveforms/triage-report.json"),
        tmp_path / "link-slice.json",
        assertion_id="assertion-0",
        before=15,
        after=5,
    )
    link_path = tmp_path / "link.json"
    write_link_report(link, link_path)
    slice_path = make_slice(tmp_path, [sig("top.a", "!")], [vc(40, "top.a", "!", "1")])

    report = reduce_relevant_signals(
        slice_path, tmp_path / "reduced.json", assertion_link_path=link_path
    )

    assert report.assertion_signal == "a_valid_stable"
    assert report.assertion_summary is not None
    assert report.assertion_link_path == link_path.resolve()


def test_malformed_slice_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "slice.json"
    bad.write_text("{}", encoding="utf-8")

    with pytest.raises(SignalReductionError, match="could not load waveform slice"):
        reduce_relevant_signals(bad, tmp_path / "reduced.json")
