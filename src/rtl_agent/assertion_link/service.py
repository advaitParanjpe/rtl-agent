from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from pydantic import ValidationError

from rtl_agent.assertion_waveform_link_models import (
    AssertionWaveformLinkReport,
    LinkedAssertion,
    LinkedWaveform,
    TimestampConversion,
)
from rtl_agent.triage_models import AssertionFailure, TriageReport, WaveformReference
from rtl_agent.waveform import (
    WaveformSliceError,
    extract_waveform_window,
    read_vcd_timescale,
    write_waveform_slice,
)

_UNIT_FEMTOSECONDS = {
    "fs": 1,
    "ps": 1_000,
    "ns": 1_000_000,
    "us": 1_000_000_000,
    "ms": 1_000_000_000_000,
    "s": 1_000_000_000_000_000,
}
_ASSERTION_TIME_RE = re.compile(
    r"^\s*([0-9][0-9_]*(?:\.[0-9]+)?)\s*(fs|ps|ns|us|ms|s)\s*$", re.IGNORECASE
)
_TIMESCALE_RE = re.compile(r"^\s*(1|10|100)\s*(fs|ps|ns|us|ms|s)\s*$", re.IGNORECASE)
_ASSERTION_ID_RE = re.compile(r"^assertion-([0-9]+)$")


class AssertionLinkError(RuntimeError):
    pass


@dataclass
class _WaveformCandidate:
    reference: WaveformReference
    resolved: Path


def link_assertion_to_waveform(
    triage_report_path: Path,
    slice_output: Path,
    *,
    assertion_index: int | None = None,
    assertion_id: str | None = None,
    before: int = 0,
    after: int = 0,
    signal_names: list[str] | None = None,
    signal_prefixes: list[str] | None = None,
    waveform_path: Path | None = None,
) -> AssertionWaveformLinkReport:
    if before < 0 or after < 0:
        raise AssertionLinkError("window before/after must not be negative")
    signal_names = signal_names or []
    signal_prefixes = signal_prefixes or []
    warnings: list[str] = []
    unresolved: list[str] = []

    triage = _load_triage(triage_report_path)
    index, assertion = _select_assertion(triage.assertion_failures, assertion_index, assertion_id)
    # Validate the assertion timestamp before any waveform work so a missing or
    # ambiguous time fails clearly on its own terms.
    _parse_assertion_time(assertion)

    candidate = _select_waveform(triage.waveform_references, waveform_path, unresolved)
    timescale = _require_timescale(candidate.resolved)
    conversion = _convert_timestamp_with_timescale(assertion, timescale)

    try:
        slice_report = extract_waveform_window(
            candidate.resolved,
            failure_time=conversion.failure_timestamp_ticks,
            before=before,
            after=after,
            signal_names=signal_names,
            signal_prefixes=signal_prefixes,
        )
        write_waveform_slice(slice_report, slice_output)
    except WaveformSliceError as exc:
        raise AssertionLinkError(f"waveform slice extraction failed: {exc}") from exc

    warnings.extend(slice_report.warnings)
    if not conversion.exact:
        warnings.append(
            "assertion time did not fall on an exact VCD tick boundary; floored to the "
            "nearest earlier tick"
        )

    return AssertionWaveformLinkReport(
        triage_report_path=triage_report_path.resolve(),
        selected_assertion=LinkedAssertion(
            assertion_id=f"assertion-{index}",
            index=index,
            source=str(assertion.source),
            line=assertion.line,
            summary=assertion.summary,
            signal_or_label=assertion.signal_or_label,
            time_context=assertion.time_context,
        ),
        selected_waveform=LinkedWaveform(
            path=candidate.reference.path,
            resolved_path=candidate.resolved,
            source=str(candidate.reference.source),
            line=candidate.reference.line,
        ),
        timestamp_conversion=conversion,
        window_before=before,
        window_after=after,
        signal_names=list(signal_names),
        signal_prefixes=list(signal_prefixes),
        waveform_slice_path=slice_output.resolve(),
        waveform_slice_sha256=_sha256(slice_output),
        slice_selected_signal_count=len(slice_report.selected_signals),
        slice_value_change_count=len(slice_report.value_changes),
        warnings=sorted(dict.fromkeys(warnings)),
        unresolved_ambiguities=sorted(dict.fromkeys(unresolved)),
        parser_notes=[
            "Assertion-to-waveform linking is deterministic and never infers root cause.",
            "Timestamp conversion uses only explicit assertion time units and the VCD "
            "timescale; ambiguous units fail rather than guess.",
        ],
    )


def write_link_report(report: AssertionWaveformLinkReport, output: Path) -> None:
    if output.exists() and output.is_dir():
        raise AssertionLinkError(f"output path is a directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_triage(triage_report_path: Path) -> TriageReport:
    try:
        return TriageReport.model_validate_json(triage_report_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise AssertionLinkError(f"could not load triage report: {triage_report_path}") from exc


def _select_assertion(
    assertions: list[AssertionFailure], index: int | None, assertion_id: str | None
) -> tuple[int, AssertionFailure]:
    if not assertions:
        raise AssertionLinkError("triage report contains no assertion findings")

    resolved_index: int | None = None
    if assertion_id is not None:
        match = _ASSERTION_ID_RE.match(assertion_id)
        if not match:
            raise AssertionLinkError(
                f"invalid assertion id: {assertion_id} (expected 'assertion-<index>')"
            )
        resolved_index = int(match.group(1))
    if index is not None:
        if resolved_index is not None and resolved_index != index:
            raise AssertionLinkError(
                "assertion id and index disagree; provide only one or matching values"
            )
        resolved_index = index

    if resolved_index is None:
        available = ", ".join(f"assertion-{position}" for position, _ in enumerate(assertions))
        raise AssertionLinkError(
            f"no assertion selected; choose one with --assertion-index/--assertion-id "
            f"from: {available}"
        )
    if resolved_index < 0 or resolved_index >= len(assertions):
        raise AssertionLinkError(
            f"assertion index out of range: {resolved_index} (0..{len(assertions) - 1})"
        )
    return resolved_index, assertions[resolved_index]


def _select_waveform(
    references: list[WaveformReference], waveform_path: Path | None, unresolved: list[str]
) -> _WaveformCandidate:
    vcd_references = [reference for reference in references if reference.path.endswith(".vcd")]
    if not vcd_references:
        other = sorted({reference.path for reference in references})
        if other:
            raise AssertionLinkError(
                "no compatible textual VCD waveform is associated with the triage report "
                f"(found unsupported formats: {', '.join(other)})"
            )
        raise AssertionLinkError("no waveform reference is associated with the triage report")

    existing: list[_WaveformCandidate] = []
    missing: list[str] = []
    for reference in vcd_references:
        resolved = reference.resolved_path or Path(reference.path)
        resolved = resolved.resolve()
        if resolved.exists() and resolved.is_file():
            existing.append(_WaveformCandidate(reference=reference, resolved=resolved))
        else:
            missing.append(reference.path)

    if not existing:
        raise AssertionLinkError(
            f"referenced VCD waveform is missing on disk: {', '.join(sorted(set(missing)))}"
        )

    distinct = _distinct_by_resolved(existing)
    if waveform_path is not None:
        target = waveform_path.resolve()
        chosen = next((item for item in distinct if item.resolved == target), None)
        if chosen is None:
            options = ", ".join(str(item.resolved) for item in distinct)
            raise AssertionLinkError(
                f"--waveform-path does not match any existing VCD reference; available: {options}"
            )
        for item in distinct:
            if item.resolved != target:
                unresolved.append(f"other waveform candidate not selected: {item.resolved}")
        return chosen

    if len(distinct) > 1:
        options = ", ".join(str(item.resolved) for item in distinct)
        raise AssertionLinkError(
            f"multiple candidate VCD waveforms; disambiguate with --waveform-path from: {options}"
        )
    return distinct[0]


def _distinct_by_resolved(candidates: list[_WaveformCandidate]) -> list[_WaveformCandidate]:
    seen: dict[Path, _WaveformCandidate] = {}
    for candidate in candidates:
        if candidate.resolved not in seen:
            seen[candidate.resolved] = candidate
    return sorted(seen.values(), key=lambda item: str(item.resolved))


def _require_timescale(vcd_path: Path) -> str:
    try:
        timescale = read_vcd_timescale(vcd_path)
    except WaveformSliceError as exc:
        raise AssertionLinkError(f"waveform is missing or malformed: {exc}") from exc
    if timescale is None:
        raise AssertionLinkError(
            "timescale conversion is ambiguous: the VCD has no $timescale header"
        )
    return timescale


def _convert_timestamp_with_timescale(
    assertion: AssertionFailure, timescale: str
) -> TimestampConversion:
    value_text, unit = _parse_assertion_time(assertion)
    magnitude, timescale_unit = _parse_timescale(timescale)

    assertion_fs = Fraction(value_text.replace("_", "")) * _UNIT_FEMTOSECONDS[unit]
    tick_fs = magnitude * _UNIT_FEMTOSECONDS[timescale_unit]
    ticks = assertion_fs / tick_fs
    floored = int(ticks)  # positive Fraction -> floor
    return TimestampConversion(
        raw_time_context=assertion.time_context or "",
        parsed_value=value_text,
        parsed_unit=unit,
        vcd_timescale=timescale,
        assertion_femtoseconds=int(assertion_fs),
        vcd_tick_femtoseconds=tick_fs,
        failure_timestamp_ticks=floored,
        exact=ticks.denominator == 1,
    )


def _parse_assertion_time(assertion: AssertionFailure) -> tuple[str, str]:
    if not assertion.time_context:
        raise AssertionLinkError(
            "selected assertion has no usable timestamp (no time context captured)"
        )
    match = _ASSERTION_TIME_RE.match(assertion.time_context)
    if not match:
        raise AssertionLinkError(
            "timestamp conversion is ambiguous: assertion time "
            f"'{assertion.time_context}' has no explicit fs/ps/ns/us/ms/s unit"
        )
    return match.group(1), match.group(2).lower()


def _parse_timescale(timescale: str) -> tuple[int, str]:
    match = _TIMESCALE_RE.match(timescale)
    if not match:
        raise AssertionLinkError(
            f"timescale conversion is ambiguous: unsupported VCD timescale '{timescale}'"
        )
    return int(match.group(1)), match.group(2).lower()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
