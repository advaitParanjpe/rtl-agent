from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from rtl_agent.waveform_comparison_models import (
    ComparisonTimeBasis,
    DivergenceInterval,
    SignalDivergence,
    TimeBasisKind,
    WaveformComparisonReport,
)
from rtl_agent.waveform_slice_models import WaveformSliceReport

_TIMESCALE_RE = re.compile(r"^\s*(1|10|100)\s*(fs|ps|ns|us|ms|s)\s*$", re.IGNORECASE)
_UNIT_FEMTOSECONDS = {
    "fs": 1,
    "ps": 1_000,
    "ns": 1_000_000,
    "us": 1_000_000_000,
    "ms": 1_000_000_000_000,
    "s": 1_000_000_000_000_000,
}
_XZ_RE = re.compile(r"[xz]", re.IGNORECASE)
_MAX_LISTED = 256
_MAX_INTERVALS = 64


class WaveformComparisonError(RuntimeError):
    pass


@dataclass
class _Timeline:
    initial: str | None
    changes: list[tuple[int, str]]  # (time in basis units, value), ascending


@dataclass
class _DivergenceResult:
    identical: bool
    first_time: int | None = None
    failing_value: str | None = None
    passing_value: str | None = None
    xz_difference: bool = False
    duration: int = 0
    intervals: list[DivergenceInterval] = field(default_factory=list)


def compare_waveforms(
    failing_slice_path: Path,
    passing_slice_path: Path,
    *,
    max_signals: int = 256,
) -> WaveformComparisonReport:
    if max_signals < 1:
        raise WaveformComparisonError("max signals must be at least 1")
    failing = _load_slice(failing_slice_path, "failing")
    passing = _load_slice(passing_slice_path, "passing")

    warnings: list[str] = []
    basis, factors = _time_basis(failing, passing, warnings)

    failing_names, failing_ambiguous = _unique_signal_names(failing)
    passing_names, passing_ambiguous = _unique_signal_names(passing)
    for name in sorted(failing_ambiguous | passing_ambiguous):
        warnings.append(f"ambiguous signal matching: duplicate signal name '{name}'")

    all_failing = {signal.name for signal in failing.selected_signals}
    all_passing = {signal.name for signal in passing.selected_signals}
    added = sorted(all_failing - all_passing)
    removed = sorted(all_passing - all_failing)
    comparable = sorted((failing_names & passing_names) - failing_ambiguous - passing_ambiguous)
    shared_count = len(all_failing & all_passing)

    if not failing.selected_signals or not passing.selected_signals:
        warnings.append("one or both slices contain no signals")
    if not (all_failing & all_passing):
        warnings.append("no shared signals between the two slices")

    diverging: list[SignalDivergence] = []
    identical: list[str] = []
    window_ok = basis.common_start <= basis.common_end
    if not window_ok:
        warnings.append("no overlapping time window between slices; signals not compared")
    else:
        failing_timelines = _timelines(failing, factors[0])
        passing_timelines = _timelines(passing, factors[1])
        for name in comparable:
            result = _compare_timeline(
                failing_timelines[name],
                passing_timelines[name],
                basis.common_start,
                basis.common_end,
            )
            if result.identical:
                identical.append(name)
                continue
            diverging.append(
                _signal_divergence(
                    name,
                    result,
                    _count_in_range(failing_timelines[name], basis),
                    _count_in_range(passing_timelines[name], basis),
                )
            )

    diverging.sort(
        key=lambda item: (
            -item.divergence_score,
            item.first_divergence_time if item.first_divergence_time is not None else 1 << 62,
            item.name,
        )
    )
    if len(diverging) > max_signals:
        warnings.append(
            f"diverging signals truncated to max-signals={max_signals}; "
            f"{len(diverging) - max_signals} dropped"
        )
        diverging = diverging[:max_signals]

    earliest_time, earliest_signals = _global_earliest(diverging)

    return WaveformComparisonReport(
        failing_slice_path=failing_slice_path.resolve(),
        passing_slice_path=passing_slice_path.resolve(),
        time_basis=basis,
        shared_signal_count=shared_count,
        added_signals=added[:_MAX_LISTED],
        removed_signals=removed[:_MAX_LISTED],
        diverging_signals=diverging,
        identical_signals=sorted(identical)[:_MAX_LISTED],
        global_earliest_divergence_time=earliest_time,
        global_earliest_divergence_signals=earliest_signals,
        warnings=sorted(dict.fromkeys(warnings)),
        parser_notes=[
            "Waveform comparison is deterministic and reports only observable value and "
            "timeline differences over a shared time basis; it never claims causal meaning.",
            "Incompatible traces are never silently aligned; timestamp normalization, when "
            "applied, is recorded explicitly in time_basis.",
        ],
    )


def write_comparison_report(report: WaveformComparisonReport, output: Path) -> None:
    if output.exists() and output.is_dir():
        raise WaveformComparisonError(f"output path is a directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_slice(path: Path, label: str) -> WaveformSliceReport:
    try:
        return WaveformSliceReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise WaveformComparisonError(f"could not load {label} waveform slice: {path}") from exc


def _time_basis(
    failing: WaveformSliceReport, passing: WaveformSliceReport, warnings: list[str]
) -> tuple[ComparisonTimeBasis, tuple[int, int]]:
    failing_ts = failing.source.timescale
    passing_ts = passing.source.timescale
    failing_factor = 1
    passing_factor = 1
    failing_tick_fs: int | None = None
    passing_tick_fs: int | None = None

    if failing_ts is not None and passing_ts is not None and _norm(failing_ts) == _norm(passing_ts):
        kind = TimeBasisKind.SHARED_TICKS
        normalized = False
        detail = f"identical timescale '{failing_ts}'; compared in shared tick units"
    else:
        failing_tick_fs = _tick_femtoseconds(failing_ts)
        passing_tick_fs = _tick_femtoseconds(passing_ts)
        if failing_tick_fs is not None and passing_tick_fs is not None:
            kind = TimeBasisKind.NORMALIZED_FEMTOSECONDS
            normalized = True
            failing_factor = failing_tick_fs
            passing_factor = passing_tick_fs
            detail = (
                f"incompatible timescales '{failing_ts}' vs '{passing_ts}'; "
                "times normalized to femtoseconds"
            )
            warnings.append(
                f"incompatible timescales normalized to femtoseconds: "
                f"'{failing_ts}' vs '{passing_ts}'"
            )
        else:
            kind = TimeBasisKind.UNNORMALIZED_TICKS
            normalized = False
            detail = (
                f"timescales '{failing_ts}' vs '{passing_ts}' are missing or unsupported; "
                "compared as raw ticks without normalization"
            )
            warnings.append(
                "timescales are ambiguous or incompatible; times compared as raw ticks "
                "without normalization"
            )

    failing_start = failing.window.requested_start * failing_factor
    failing_end = failing.window.requested_end * failing_factor
    passing_start = passing.window.requested_start * passing_factor
    passing_end = passing.window.requested_end * passing_factor
    if failing_start != passing_start or failing_end != passing_end:
        warnings.append(
            "window mismatch; comparison restricted to the overlapping range "
            f"[{max(failing_start, passing_start)}, {min(failing_end, passing_end)}]"
        )
    basis = ComparisonTimeBasis(
        kind=kind,
        failing_timescale=failing_ts,
        passing_timescale=passing_ts,
        normalized=normalized,
        failing_tick_femtoseconds=failing_tick_fs,
        passing_tick_femtoseconds=passing_tick_fs,
        common_start=max(failing_start, passing_start),
        common_end=min(failing_end, passing_end),
        detail=detail,
    )
    return basis, (failing_factor, passing_factor)


def _unique_signal_names(slice_report: WaveformSliceReport) -> tuple[set[str], set[str]]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for signal in slice_report.selected_signals:
        if signal.name in seen:
            duplicates.add(signal.name)
        seen.add(signal.name)
    return seen - duplicates, duplicates


def _timelines(slice_report: WaveformSliceReport, factor: int) -> dict[str, _Timeline]:
    initials: dict[str, str | None] = {}
    for initial in slice_report.initial_values:
        initials.setdefault(initial.signal, initial.value)
    changes: dict[str, list[tuple[int, str]]] = {}
    for change in slice_report.value_changes:
        changes.setdefault(change.signal, []).append((change.time * factor, change.value))
    timelines: dict[str, _Timeline] = {}
    for signal in slice_report.selected_signals:
        ordered = sorted(changes.get(signal.name, []), key=lambda item: item[0])
        timelines[signal.name] = _Timeline(initial=initials.get(signal.name), changes=ordered)
    return timelines


def _compare_timeline(
    failing: _Timeline, passing: _Timeline, start: int, end: int
) -> _DivergenceResult:
    boundaries = {start}
    for time, _ in failing.changes:
        if start <= time <= end:
            boundaries.add(time)
    for time, _ in passing.changes:
        if start <= time <= end:
            boundaries.add(time)
    points = sorted(boundaries)

    intervals: list[DivergenceInterval] = []
    duration = 0
    first_time: int | None = None
    failing_value: str | None = None
    passing_value: str | None = None
    xz_difference = False
    for index, segment_start in enumerate(points):
        segment_end = points[index + 1] if index + 1 < len(points) else end
        if segment_end <= segment_start:
            continue
        failing_sample = _sample(failing, segment_start)
        passing_sample = _sample(passing, segment_start)
        if failing_sample == passing_sample:
            continue
        if first_time is None:
            first_time = segment_start
            failing_value = failing_sample
            passing_value = passing_sample
        if _has_xz(failing_sample) != _has_xz(passing_sample):
            xz_difference = True
        duration += segment_end - segment_start
        if intervals and intervals[-1].end == segment_start:
            intervals[-1] = DivergenceInterval(start=intervals[-1].start, end=segment_end)
        elif len(intervals) < _MAX_INTERVALS:
            intervals.append(DivergenceInterval(start=segment_start, end=segment_end))
    return _DivergenceResult(
        identical=first_time is None,
        first_time=first_time,
        failing_value=failing_value,
        passing_value=passing_value,
        xz_difference=xz_difference,
        duration=duration,
        intervals=intervals,
    )


def _signal_divergence(
    name: str, result: _DivergenceResult, failing_transitions: int, passing_transitions: int
) -> SignalDivergence:
    score = result.duration * 10 + len(result.intervals) + (5 if result.xz_difference else 0)
    return SignalDivergence(
        name=name,
        identical=False,
        first_divergence_time=result.first_time,
        failing_value_at_divergence=result.failing_value,
        passing_value_at_divergence=result.passing_value,
        failing_transition_count=failing_transitions,
        passing_transition_count=passing_transitions,
        xz_difference=result.xz_difference,
        divergence_duration=result.duration,
        divergence_intervals=result.intervals,
        divergence_score=score,
    )


def _count_in_range(timeline: _Timeline, basis: ComparisonTimeBasis) -> int:
    return sum(1 for time, _ in timeline.changes if basis.common_start <= time <= basis.common_end)


def _global_earliest(diverging: list[SignalDivergence]) -> tuple[int | None, list[str]]:
    times = [
        signal.first_divergence_time
        for signal in diverging
        if signal.first_divergence_time is not None
    ]
    if not times:
        return None, []
    earliest = min(times)
    signals = sorted(
        signal.name for signal in diverging if signal.first_divergence_time == earliest
    )
    return earliest, signals


def _sample(timeline: _Timeline, time: int) -> str | None:
    value = timeline.initial
    for change_time, change_value in timeline.changes:
        if change_time <= time:
            value = change_value
        else:
            break
    return value


def _has_xz(value: str | None) -> bool:
    return value is not None and bool(_XZ_RE.search(value))


def _tick_femtoseconds(timescale: str | None) -> int | None:
    if timescale is None:
        return None
    match = _TIMESCALE_RE.match(timescale)
    if not match:
        return None
    return int(match.group(1)) * _UNIT_FEMTOSECONDS[match.group(2).lower()]


def _norm(timescale: str) -> str:
    return re.sub(r"\s+", "", timescale).lower()
