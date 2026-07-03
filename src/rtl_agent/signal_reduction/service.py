from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from rtl_agent.assertion_waveform_link_models import AssertionWaveformLinkReport
from rtl_agent.relevant_signal_models import (
    ExcludedSignalSummary,
    RankedSignal,
    RelevantSignalReductionReport,
    SignalRelevanceCriterion,
    SignalRelevanceReason,
)
from rtl_agent.waveform import WaveformSliceError, write_waveform_slice
from rtl_agent.waveform_slice_models import WaveformSliceReport

# Deterministic, documented criterion weights. Higher means stronger explicit
# textual evidence that a signal is relevant to the failure.
_POINTS = {
    SignalRelevanceCriterion.ASSERTION_NAMED: 100,
    SignalRelevanceCriterion.TRANSITION_AT_FAILURE: 40,
    SignalRelevanceCriterion.TRANSITION_IN_WINDOW: 20,
    SignalRelevanceCriterion.UNKNOWN_OR_HIGHZ: 25,
    SignalRelevanceCriterion.HIERARCHY_PROXIMITY: 15,
}
_MAX_EXCLUDED_LISTED = 32
_XZ_RE = re.compile(r"[xz]", re.IGNORECASE)


class SignalReductionError(RuntimeError):
    pass


@dataclass
class _SignalEvidence:
    transition_count: int = 0
    transition_at_failure: bool = False
    nearest_distance: int | None = None
    has_unknown_or_highz: bool = False
    times: list[int] = field(default_factory=list)


def reduce_relevant_signals(
    waveform_slice_path: Path,
    reduced_slice_output: Path,
    *,
    assertion_link_path: Path | None = None,
    assertion_signal: str | None = None,
    assertion_summary: str | None = None,
    max_signals: int = 32,
) -> RelevantSignalReductionReport:
    if max_signals < 1:
        raise SignalReductionError("max signals must be at least 1")

    slice_report = _load_slice(waveform_slice_path)
    resolved_signal, resolved_summary = _resolve_assertion_context(
        assertion_link_path, assertion_signal, assertion_summary
    )

    failure_time = slice_report.window.failure_time
    evidence = _collect_evidence(slice_report, failure_time)
    anchor = _hierarchy_anchor(slice_report, resolved_signal)
    summary_tokens = _tokenize(resolved_summary)

    warnings: list[str] = []
    ranked: list[RankedSignal] = []
    excluded_no_evidence: list[str] = []
    for signal in slice_report.selected_signals:
        signal_evidence = evidence.get(signal.identifier, _SignalEvidence())
        reasons = _score_signal(
            signal_name=signal.name,
            evidence=signal_evidence,
            assertion_signal=resolved_signal,
            summary_tokens=summary_tokens,
            anchor=anchor,
        )
        if not reasons:
            excluded_no_evidence.append(signal.name)
            continue
        ranked.append(
            RankedSignal(
                name=signal.name,
                identifier=signal.identifier,
                score=sum(reason.points for reason in reasons),
                transition_count=signal_evidence.transition_count,
                nearest_transition_distance=signal_evidence.nearest_distance,
                reasons=reasons,
            )
        )

    ranked.sort(key=lambda item: (-item.score, item.name, item.identifier))
    retained = ranked[:max_signals]
    over_cap = [item.name for item in ranked[max_signals:]]

    if not slice_report.selected_signals:
        warnings.append("waveform slice contains no signals")
    elif not ranked:
        warnings.append("no signals matched any relevance criterion")
    if over_cap:
        warnings.append(
            f"retained signals capped at max-signals={max_signals}; "
            f"{len(over_cap)} lower-scored signal(s) dropped"
        )

    retained_names = {item.name for item in retained}
    reduced_slice = _build_reduced_slice(slice_report, retained_names)
    try:
        write_waveform_slice(reduced_slice, reduced_slice_output)
    except WaveformSliceError as exc:
        raise SignalReductionError(f"could not write reduced slice: {exc}") from exc

    excluded = _excluded_summaries(excluded_no_evidence, over_cap)

    return RelevantSignalReductionReport(
        waveform_slice_path=waveform_slice_path.resolve(),
        assertion_link_path=assertion_link_path.resolve() if assertion_link_path else None,
        assertion_signal=resolved_signal,
        assertion_summary=resolved_summary,
        failure_time=failure_time,
        max_signals=max_signals,
        total_candidate_signals=len(slice_report.selected_signals),
        retained_signals=retained,
        excluded=excluded,
        reduced_slice_path=reduced_slice_output.resolve(),
        reduced_slice_sha256=_sha256(reduced_slice_output),
        warnings=sorted(dict.fromkeys(warnings)),
        parser_notes=[
            "Relevant-signal reduction is deterministic and ranks signals only from "
            "explicit textual and transition evidence in the existing slice.",
            "It never traces signal dependencies, interprets waveform semantics, or "
            "claims root cause; the reduced set is a strict subset of the input slice.",
        ],
    )


def write_reduction_report(report: RelevantSignalReductionReport, output: Path) -> None:
    if output.exists() and output.is_dir():
        raise SignalReductionError(f"output path is a directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_slice(waveform_slice_path: Path) -> WaveformSliceReport:
    try:
        return WaveformSliceReport.model_validate_json(
            waveform_slice_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError, ValueError) as exc:
        raise SignalReductionError(f"could not load waveform slice: {waveform_slice_path}") from exc


def _resolve_assertion_context(
    assertion_link_path: Path | None,
    assertion_signal: str | None,
    assertion_summary: str | None,
) -> tuple[str | None, str | None]:
    link_signal: str | None = None
    link_summary: str | None = None
    if assertion_link_path is not None:
        try:
            link = AssertionWaveformLinkReport.model_validate_json(
                assertion_link_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as exc:
            raise SignalReductionError(
                f"could not load assertion-link report: {assertion_link_path}"
            ) from exc
        link_signal = link.selected_assertion.signal_or_label
        link_summary = link.selected_assertion.summary
    # Explicit flags take precedence over the linked assertion context.
    return assertion_signal or link_signal, assertion_summary or link_summary


def _collect_evidence(
    slice_report: WaveformSliceReport, failure_time: int
) -> dict[str, _SignalEvidence]:
    evidence: dict[str, _SignalEvidence] = {}
    for change in slice_report.value_changes:
        item = evidence.setdefault(change.identifier, _SignalEvidence())
        item.transition_count += 1
        item.times.append(change.time)
        distance = abs(change.time - failure_time)
        if item.nearest_distance is None or distance < item.nearest_distance:
            item.nearest_distance = distance
        if change.time == failure_time:
            item.transition_at_failure = True
        if _XZ_RE.search(change.value):
            item.has_unknown_or_highz = True
    for initial in slice_report.initial_values:
        if initial.value and _XZ_RE.search(initial.value):
            evidence.setdefault(initial.identifier, _SignalEvidence()).has_unknown_or_highz = True
    return evidence


def _score_signal(
    signal_name: str,
    evidence: _SignalEvidence,
    assertion_signal: str | None,
    summary_tokens: set[str],
    anchor: str | None,
) -> list[SignalRelevanceReason]:
    reasons: list[SignalRelevanceReason] = []
    leaf = signal_name.rsplit(".", 1)[-1]

    if assertion_signal is not None or summary_tokens:
        named_detail = _assertion_named_detail(signal_name, leaf, assertion_signal, summary_tokens)
        if named_detail is not None:
            reasons.append(_reason(SignalRelevanceCriterion.ASSERTION_NAMED, named_detail))

    if evidence.transition_at_failure:
        reasons.append(
            _reason(
                SignalRelevanceCriterion.TRANSITION_AT_FAILURE,
                "value change at the failure timestamp",
            )
        )
    if evidence.transition_count > 0:
        reasons.append(
            _reason(
                SignalRelevanceCriterion.TRANSITION_IN_WINDOW,
                f"{evidence.transition_count} value change(s) in window; "
                f"nearest distance {evidence.nearest_distance}",
            )
        )
    if evidence.has_unknown_or_highz:
        reasons.append(
            _reason(
                SignalRelevanceCriterion.UNKNOWN_OR_HIGHZ,
                "carries unknown (x) or high-impedance (z) values in window",
            )
        )
    if anchor is not None and signal_name != anchor:
        shared = _shared_parent_scope(signal_name, anchor)
        if shared is not None:
            reasons.append(
                _reason(
                    SignalRelevanceCriterion.HIERARCHY_PROXIMITY,
                    f"shares the assertion signal's parent scope '{shared}'",
                )
            )
    return reasons


def _assertion_named_detail(
    signal_name: str, leaf: str, assertion_signal: str | None, summary_tokens: set[str]
) -> str | None:
    if assertion_signal is not None:
        if signal_name == assertion_signal:
            return f"signal name matches the assertion signal '{assertion_signal}'"
        if leaf == assertion_signal.rsplit(".", 1)[-1]:
            return f"leaf name matches the assertion signal '{assertion_signal}'"
    if leaf.lower() in summary_tokens:
        return "leaf name appears in the assertion summary text"
    return None


def _hierarchy_anchor(
    slice_report: WaveformSliceReport, assertion_signal: str | None
) -> str | None:
    if assertion_signal is None:
        return None
    if "." in assertion_signal:
        return assertion_signal
    leaf = assertion_signal.rsplit(".", 1)[-1]
    candidates = sorted(
        signal.name
        for signal in slice_report.selected_signals
        if signal.name.rsplit(".", 1)[-1] == leaf
    )
    return candidates[0] if candidates else None


def _shared_parent_scope(signal_name: str, anchor: str) -> str | None:
    anchor_parts = anchor.split(".")
    signal_parts = signal_name.split(".")
    if len(anchor_parts) < 2 or len(signal_parts) < 2:
        return None
    anchor_parent = anchor_parts[:-1]
    if signal_parts[: len(anchor_parent)] == anchor_parent:
        return ".".join(anchor_parent)
    return None


def _build_reduced_slice(
    slice_report: WaveformSliceReport, retained_names: set[str]
) -> WaveformSliceReport:
    signals = [signal for signal in slice_report.selected_signals if signal.name in retained_names]
    value_changes = [
        change for change in slice_report.value_changes if change.signal in retained_names
    ]
    initial_values = [
        initial for initial in slice_report.initial_values if initial.signal in retained_names
    ]
    statistics = slice_report.parse_statistics.model_copy(
        update={
            "selected_signals": len(signals),
            "value_changes_in_window": len(value_changes),
        }
    )
    return WaveformSliceReport(
        source=slice_report.source,
        window=slice_report.window,
        selected_signals=signals,
        initial_values=initial_values,
        value_changes=value_changes,
        warnings=[
            *slice_report.warnings,
            "reduced to relevant signals by deterministic evidence ranking",
        ],
        parser_notes=slice_report.parser_notes,
        parse_statistics=statistics,
    )


def _excluded_summaries(no_evidence: list[str], over_cap: list[str]) -> list[ExcludedSignalSummary]:
    summaries: list[ExcludedSignalSummary] = []
    if no_evidence:
        ordered = sorted(no_evidence)
        summaries.append(
            ExcludedSignalSummary(
                reason="no relevance evidence matched",
                count=len(ordered),
                signals=ordered[:_MAX_EXCLUDED_LISTED],
            )
        )
    if over_cap:
        ordered = sorted(over_cap)
        summaries.append(
            ExcludedSignalSummary(
                reason="scored but dropped by max-signals cap",
                count=len(ordered),
                signals=ordered[:_MAX_EXCLUDED_LISTED],
            )
        )
    return summaries


def _tokenize(text: str | None) -> set[str]:
    if not text:
        return set()
    return {token.lower() for token in re.findall(r"[A-Za-z_][A-Za-z0-9_$]*", text)}


def _reason(criterion: SignalRelevanceCriterion, detail: str) -> SignalRelevanceReason:
    return SignalRelevanceReason(criterion=criterion, points=_POINTS[criterion], detail=detail)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
