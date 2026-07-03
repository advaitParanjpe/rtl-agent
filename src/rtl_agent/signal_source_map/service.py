from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from rtl_agent.repository_map import RepositoryMap
from rtl_agent.signal_source_map_models import (
    DeclarationCandidate,
    SignalMappingStatus,
    SignalSourceMapping,
    SignalSourceMapReport,
)
from rtl_agent.waveform_comparison_models import WaveformComparisonReport
from rtl_agent.waveform_slice_models import WaveformSliceReport

# Score tiers. Scope (non-leaf) exact-name matches to a declaration are the
# strongest evidence; leaf and case-insensitive matches are weaker.
_SCOPE_EXACT = 100
_LEAF_EXACT = 60
_SCOPE_CI = 40
_LEAF_CI = 20
_MAX_CANDIDATES_PER_SIGNAL = 64


class SignalSourceMapError(RuntimeError):
    pass


@dataclass(frozen=True)
class _Declaration:
    name: str
    kind: str
    file_path: str
    line: int


def map_signals_to_source(
    repository_map_path: Path,
    *,
    signal_names: list[str] | None = None,
    waveform_slice_path: Path | None = None,
    comparison_path: Path | None = None,
    max_signals: int = 1024,
) -> SignalSourceMapReport:
    if max_signals < 1:
        raise SignalSourceMapError("max signals must be at least 1")

    repository_map = _load_repository_map(repository_map_path)
    index_exact, index_ci = _declaration_index(repository_map)

    warnings: list[str] = []
    signals = _collect_signals(signal_names or [], waveform_slice_path, comparison_path, warnings)
    if not signals:
        warnings.append("no signals were provided to map")
    if len(signals) > max_signals:
        warnings.append(
            f"signals truncated to max-signals={max_signals}; {len(signals) - max_signals} dropped"
        )
        signals = signals[:max_signals]

    mappings = [_map_signal(signal, index_exact, index_ci) for signal in signals]
    counts = {status: 0 for status in SignalMappingStatus}
    for mapping in mappings:
        counts[SignalMappingStatus(mapping.status)] += 1

    return SignalSourceMapReport(
        repository_map_path=repository_map_path.resolve(),
        waveform_slice_path=waveform_slice_path.resolve() if waveform_slice_path else None,
        comparison_path=comparison_path.resolve() if comparison_path else None,
        total_signals=len(mappings),
        exact_count=counts[SignalMappingStatus.EXACT],
        probable_count=counts[SignalMappingStatus.PROBABLE],
        ambiguous_count=counts[SignalMappingStatus.AMBIGUOUS],
        unresolved_count=counts[SignalMappingStatus.UNRESOLVED],
        mappings=mappings,
        warnings=sorted(dict.fromkeys(warnings)),
        parser_notes=[
            "Signal-to-source mapping is deterministic and evidence-based: it matches "
            "hierarchical signal path components against repository-map declaration names only.",
            "It never elaborates semantics, traces connectivity or drivers, or claims causal "
            "meaning; all candidate declarations are preserved where ambiguity exists.",
        ],
    )


def write_signal_source_map(report: SignalSourceMapReport, output: Path) -> None:
    if output.exists() and output.is_dir():
        raise SignalSourceMapError(f"output path is a directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_repository_map(path: Path) -> RepositoryMap:
    try:
        return RepositoryMap.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise SignalSourceMapError(f"could not load repository map: {path}") from exc


def _declaration_index(
    repository_map: RepositoryMap,
) -> tuple[dict[str, list[_Declaration]], dict[str, list[_Declaration]]]:
    exact: dict[str, list[_Declaration]] = {}
    lower: dict[str, list[_Declaration]] = {}
    for file_record in repository_map.files:
        if file_record.source is None:
            continue
        for declaration in file_record.source.declarations:
            item = _Declaration(
                name=declaration.name,
                kind=str(declaration.kind),
                file_path=file_record.path,
                line=declaration.line,
            )
            exact.setdefault(declaration.name, []).append(item)
            lower.setdefault(declaration.name.lower(), []).append(item)
    return exact, lower


def _collect_signals(
    signal_names: list[str],
    waveform_slice_path: Path | None,
    comparison_path: Path | None,
    warnings: list[str],
) -> list[str]:
    names: list[str] = list(signal_names)
    if waveform_slice_path is not None:
        slice_report = _load_slice(waveform_slice_path)
        names.extend(signal.name for signal in slice_report.selected_signals)
    if comparison_path is not None:
        comparison = _load_comparison(comparison_path)
        names.extend(signal.name for signal in comparison.diverging_signals)
        names.extend(comparison.identical_signals)
    return sorted(dict.fromkeys(name for name in names if name))


def _load_slice(path: Path) -> WaveformSliceReport:
    try:
        return WaveformSliceReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise SignalSourceMapError(f"could not load waveform slice: {path}") from exc


def _load_comparison(path: Path) -> WaveformComparisonReport:
    try:
        return WaveformComparisonReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise SignalSourceMapError(f"could not load comparison report: {path}") from exc


def _map_signal(
    signal: str,
    index_exact: dict[str, list[_Declaration]],
    index_ci: dict[str, list[_Declaration]],
) -> SignalSourceMapping:
    elements = [part for part in signal.split(".") if part]
    leaf = elements[-1] if elements else signal
    scope = elements[:-1]

    candidates: list[DeclarationCandidate] = []
    for index, element in enumerate(elements):
        is_leaf = index == len(elements) - 1
        role = "leaf" if is_leaf else "scope"
        depth_bonus = len(elements) - index
        exact_matches = index_exact.get(element, [])
        if exact_matches:
            base = _LEAF_EXACT if is_leaf else _SCOPE_EXACT + depth_bonus
            for declaration in exact_matches:
                candidates.append(_candidate(element, role, declaration, base, "exact name match"))
            continue
        ci_matches = [
            declaration
            for declaration in index_ci.get(element.lower(), [])
            if declaration.name != element
        ]
        if ci_matches:
            base = _LEAF_CI if is_leaf else _SCOPE_CI + depth_bonus
            for declaration in ci_matches:
                candidates.append(
                    _candidate(element, role, declaration, base, "case-insensitive name match")
                )

    candidates.sort(
        key=lambda item: (-item.score, item.file_path, item.line, item.declaration_name)
    )
    candidates = candidates[:_MAX_CANDIDATES_PER_SIGNAL]
    status, reason = _classify(signal, leaf, candidates)
    return SignalSourceMapping(
        signal=signal, leaf=leaf, scope=scope, status=status, reason=reason, candidates=candidates
    )


def _candidate(
    element: str, role: str, declaration: _Declaration, score: int, kind_reason: str
) -> DeclarationCandidate:
    reason = (
        f"{kind_reason} of {role} component '{element}' to {declaration.kind} "
        f"declaration '{declaration.name}' at {declaration.file_path}:{declaration.line}"
    )
    return DeclarationCandidate(
        declaration_name=declaration.name,
        declaration_kind=declaration.kind,
        file_path=declaration.file_path,
        line=declaration.line,
        matched_element=element,
        matched_role=role,
        match_reason=reason,
        score=score,
    )


def _classify(
    signal: str, leaf: str, candidates: list[DeclarationCandidate]
) -> tuple[SignalMappingStatus, str]:
    if not candidates:
        return (
            SignalMappingStatus.UNRESOLVED,
            "no declaration in the repository map matches any component of the signal path",
        )
    top_score = candidates[0].score
    best = [candidate for candidate in candidates if candidate.score == top_score]
    for candidate in best:
        candidate.primary = True
    distinct = {
        (candidate.file_path, candidate.line, candidate.declaration_name) for candidate in best
    }
    primary = best[0]

    if len(distinct) > 1:
        locations = ", ".join(f"{candidate.file_path}:{candidate.line}" for candidate in best)
        return (
            SignalMappingStatus.AMBIGUOUS,
            f"component '{primary.matched_element}' matches multiple declarations: {locations}",
        )
    if primary.matched_role == "scope" and primary.score >= _SCOPE_EXACT:
        return (
            SignalMappingStatus.EXACT,
            f"leaf '{leaf}' resolves under {primary.declaration_kind} '{primary.declaration_name}' "
            f"at {primary.file_path}:{primary.line}",
        )
    return (
        SignalMappingStatus.PROBABLE,
        f"best match is {primary.declaration_kind} '{primary.declaration_name}' at "
        f"{primary.file_path}:{primary.line} via {primary.matched_role} component "
        f"'{primary.matched_element}'",
    )
