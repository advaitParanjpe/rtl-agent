from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from rtl_agent.counterfactual_models import CounterfactualExperimentReport
from rtl_agent.failure_family.report import render_family_markdown, write_family_report
from rtl_agent.failure_family_models import (
    ClusteringInputSummary,
    ClusterStrictness,
    ExactDuplicateSubgroup,
    ExcludedInput,
    FailureFamilyClusterReport,
    FailureFamilyGroup,
    InsufficientEvidenceEntry,
    MemberReference,
    RelatedFamilyLink,
    RepresentativeFingerprint,
)
from rtl_agent.failure_fingerprint import (
    FailureFingerprintError,
    compare_fingerprint_reports,
    fingerprint_run,
)
from rtl_agent.failure_fingerprint_models import (
    FAILURE_FINGERPRINT_SCHEMA_VERSION,
    FailureFingerprintReport,
    FingerprintMatchKind,
)

_PARSER_NOTES = [
    "Failure-family clustering is deterministic and read-only. It groups existing failure "
    "fingerprints by their family digest and reuses the existing fingerprint comparison "
    "semantics; it reruns no simulation and performs no new waveform or RTL analysis.",
    "A family groups runs that share an observed failure mechanism. It is not a root-cause "
    "claim, and insufficient-evidence fingerprints are reported separately, never forced "
    "into a confident family.",
]

# Component list fields that define fingerprint evidence completeness and comparison.
_COMPONENT_FIELDS = [
    "assertion_identity",
    "terminal_outcome",
    "failure_time_characteristics",
    "earliest_divergent_signals",
    "ranked_divergent_signals",
    "ranked_relevant_signals",
    "transition_xz_characteristics",
    "mapped_sources",
    "driver_dependency_shape",
    "unresolved_markers",
    "ambiguous_markers",
    "graph_shape",
]

# Bound the pairwise related-family comparison to keep runtime deterministic and small.
_MAX_FAMILIES_FOR_LINKS = 48


class FailureFamilyError(RuntimeError):
    pass


@dataclass
class _Loaded:
    source_path: str
    origin: str
    report: FailureFingerprintReport


def cluster_fingerprints(
    *,
    fingerprint_paths: list[Path],
    fingerprint_dir: Path | None = None,
    strict: bool = False,
) -> FailureFamilyClusterReport:
    """Group existing failure fingerprints into observed failure families (read-only)."""

    inputs, duplicate_paths = _collect_input_paths(fingerprint_paths, fingerprint_dir)
    if not inputs:
        raise FailureFamilyError("no fingerprint inputs were provided")

    loaded: list[_Loaded] = []
    excluded: list[ExcludedInput] = []
    warnings: list[str] = []
    derived_count = 0

    for display, path in inputs:
        try:
            resolved_inputs = _load_input(display, path)
        except FailureFamilyError as exc:
            if strict:
                raise
            excluded.append(ExcludedInput(source_path=display, reason=str(exc)))
            warnings.append(f"excluded invalid input: {display} ({exc})")
            continue
        for item in resolved_inputs:
            if item.origin != "fingerprint":
                derived_count += 1
            loaded.append(item)

    if not loaded and not excluded:
        raise FailureFamilyError("no usable fingerprints were found in the inputs")

    sufficient = [item for item in loaded if not item.report.insufficient_evidence]
    insufficient = _insufficient_entries(
        item for item in loaded if item.report.insufficient_evidence
    )

    families, representatives = _build_families(sufficient)
    if len(families) > _MAX_FAMILIES_FOR_LINKS:
        warnings.append(
            f"related-family link computation skipped: {len(families)} families exceed the "
            f"bound of {_MAX_FAMILIES_FOR_LINKS}"
        )
        related: list[RelatedFamilyLink] = []
    else:
        related = _link_families(families, representatives)
    outliers = sorted(family.family_digest for family in families if family.is_outlier)

    exact_duplicate_count = sum(
        len(subgroup.members) - 1
        for family in families
        for subgroup in family.exact_duplicate_subgroups
        if subgroup.size > 1
    )

    summary = ClusteringInputSummary(
        strictness=ClusterStrictness.STRICT if strict else ClusterStrictness.PERMISSIVE,
        total_inputs=len(inputs),
        valid_fingerprints=len(loaded),
        excluded_invalid=len(excluded),
        duplicate_paths_ignored=duplicate_paths,
        derived_from_counterfactual=derived_count,
        family_count=len(families),
        exact_duplicate_count=exact_duplicate_count,
        outlier_count=len(outliers),
        insufficient_evidence_count=len(insufficient),
    )
    return FailureFamilyClusterReport(
        input_summary=summary,
        families=families,
        insufficient_evidence=insufficient,
        outliers=outliers,
        related_family_links=related,
        excluded_inputs=sorted(excluded, key=lambda item: item.source_path),
        warnings=sorted(dict.fromkeys(warnings)),
        parser_notes=_PARSER_NOTES,
    )


def write_cluster_report(report: FailureFamilyClusterReport, output: Path) -> None:
    write_family_report(report, output)


def render_cluster_markdown(report: FailureFamilyClusterReport, output: Path) -> None:
    render_family_markdown(report, output)


def _collect_input_paths(
    fingerprint_paths: list[Path], fingerprint_dir: Path | None
) -> tuple[list[tuple[str, Path]], int]:
    ordered: list[tuple[str, Path]] = [(str(path), path) for path in fingerprint_paths]
    if fingerprint_dir is not None:
        if not fingerprint_dir.is_dir():
            raise FailureFamilyError(f"fingerprint directory not found: {fingerprint_dir}")
        for path in sorted(fingerprint_dir.glob("*.json")):
            ordered.append((path.name, path))
    seen: set[Path] = set()
    unique: list[tuple[str, Path]] = []
    duplicates = 0
    for display, path in ordered:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen:
            duplicates += 1
            continue
        seen.add(resolved)
        unique.append((display, path))
    return unique, duplicates


def _load_input(display: str, path: Path) -> list[_Loaded]:
    if not path.exists() or not path.is_file():
        raise FailureFamilyError(f"input file not found: {display}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise FailureFamilyError(f"input is not readable JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise FailureFamilyError("input is not a JSON object")

    if "family_digest" in raw and "exact_digest" in raw:
        return [_load_fingerprint_input(display, raw)]
    if "outcome" in raw and "baseline" in raw and "intervention" in raw:
        return _load_counterfactual_input(display, path, raw)
    raise FailureFamilyError("input is neither a failure fingerprint nor a counterfactual report")


def _load_fingerprint_input(display: str, raw: dict[str, object]) -> _Loaded:
    version = raw.get("schema_version")
    if version != FAILURE_FINGERPRINT_SCHEMA_VERSION:
        raise FailureFamilyError(
            f"unsupported fingerprint schema version: {version} "
            f"(expected {FAILURE_FINGERPRINT_SCHEMA_VERSION})"
        )
    try:
        report = FailureFingerprintReport.model_validate(raw)
    except (ValidationError, ValueError) as exc:
        raise FailureFamilyError(f"malformed failure fingerprint: {exc}") from exc
    return _Loaded(source_path=display, origin="fingerprint", report=report)


def _load_counterfactual_input(display: str, path: Path, raw: dict[str, object]) -> list[_Loaded]:
    try:
        experiment = CounterfactualExperimentReport.model_validate(raw)
    except (ValidationError, ValueError) as exc:
        raise FailureFamilyError(f"malformed counterfactual report: {exc}") from exc

    derived: list[_Loaded] = []
    experiment_dir = path.resolve().parent
    candidates = [
        ("counterfactual_baseline", Path(experiment.baseline.run_dir)),
        ("counterfactual_intervention", experiment_dir / "intervention-run"),
    ]
    for origin, run_dir in candidates:
        if not (run_dir / "run-manifest.json").exists():
            continue
        try:
            report = fingerprint_run(run_dir)
        except FailureFingerprintError as exc:
            raise FailureFamilyError(f"could not fingerprint {origin} run: {exc}") from exc
        derived.append(
            _Loaded(
                source_path=f"{display}::{origin.split('_', 1)[1]}", origin=origin, report=report
            )
        )
    if not derived:
        raise FailureFamilyError("counterfactual report references no fingerprintable runs")
    return derived


def _insufficient_entries(items: object) -> list[InsufficientEvidenceEntry]:
    assert hasattr(items, "__iter__")
    entries = [
        InsufficientEvidenceEntry(
            source_path=item.source_path,
            exact_digest=item.report.exact_digest,
            family_digest=item.report.family_digest,
            reasons=list(item.report.insufficient_evidence),
        )
        for item in items
    ]
    return sorted(entries, key=lambda entry: (entry.source_path, entry.exact_digest))


def _build_families(
    sufficient: list[_Loaded],
) -> tuple[list[FailureFamilyGroup], dict[str, FailureFingerprintReport]]:
    by_family: dict[str, list[_Loaded]] = {}
    for item in sufficient:
        by_family.setdefault(item.report.family_digest, []).append(item)

    families: list[FailureFamilyGroup] = []
    representatives: dict[str, FailureFingerprintReport] = {}
    for family_digest, members in sorted(by_family.items()):
        group, representative = _build_family(family_digest, members)
        families.append(group)
        representatives[family_digest] = representative.report
    return families, representatives


def _build_family(family_digest: str, members: list[_Loaded]) -> tuple[FailureFamilyGroup, _Loaded]:
    ordered = sorted(members, key=lambda item: (item.report.exact_digest, item.source_path))
    representative = _select_representative(ordered)

    by_exact: dict[str, list[str]] = {}
    for item in ordered:
        by_exact.setdefault(item.report.exact_digest, []).append(item.source_path)
    subgroups = [
        ExactDuplicateSubgroup(exact_digest=digest, size=len(paths), members=sorted(paths))
        for digest, paths in sorted(by_exact.items())
    ]

    reports = [item.report for item in ordered]
    group = FailureFamilyGroup(
        family_digest=family_digest,
        size=len(ordered),
        is_outlier=len(ordered) == 1,
        description=_family_description(representative.report, len(ordered)),
        representative=RepresentativeFingerprint(
            source_path=representative.source_path,
            exact_digest=representative.report.exact_digest,
            family_digest=family_digest,
            completeness_score=_completeness(representative.report),
            selection_reason=_selection_reason(representative.report),
        ),
        members=[
            MemberReference(
                source_path=item.source_path,
                origin=item.origin,
                exact_digest=item.report.exact_digest,
                family_digest=item.report.family_digest,
            )
            for item in ordered
        ],
        exact_duplicate_subgroups=subgroups,
        observed_time_range=_observed_time_range(reports),
        assertion_identities=_union(reports, "assertion_identity"),
        earliest_divergent_signals_union=_union(reports, "earliest_divergent_signals"),
        earliest_divergent_signals_intersection=_intersection(
            reports, "earliest_divergent_signals"
        ),
        relevant_signals_union=_union(reports, "ranked_relevant_signals"),
        relevant_signals_intersection=_intersection(reports, "ranked_relevant_signals"),
        mapped_sources=_union(reports, "mapped_sources"),
        ambiguity_markers=_union(reports, "ambiguous_markers"),
        insufficient_evidence_markers=_union(reports, "insufficient_evidence"),
    )
    return group, representative


def _select_representative(members: list[_Loaded]) -> _Loaded:
    # Most complete evidence; ties broken by stable exact_digest then source path.
    return max(
        members,
        key=lambda item: (
            _completeness(item.report),
            _total_values(item.report),
            _neg_key(item.report.exact_digest),
            _neg_key(item.source_path),
        ),
    )


def _completeness(report: FailureFingerprintReport) -> int:
    return sum(1 for name in _COMPONENT_FIELDS if getattr(report, name))


def _total_values(report: FailureFingerprintReport) -> int:
    return sum(len(getattr(report, name)) for name in _COMPONENT_FIELDS)


def _neg_key(value: str) -> tuple[int, ...]:
    # Smaller string sorts as "greater" so max() prefers the lexicographically first.
    return tuple(-ord(char) for char in value)


def _selection_reason(report: FailureFingerprintReport) -> str:
    score = _completeness(report)
    return (
        f"highest evidence completeness (score {score} of {len(_COMPONENT_FIELDS)}, "
        f"{_total_values(report)} total values); ties broken by exact digest then source path"
    )


def _family_description(report: FailureFingerprintReport, size: int) -> str:
    signals = ", ".join(report.earliest_divergent_signals) or "(no earliest signal recorded)"
    times = ", ".join(report.failure_time_characteristics) or "(no time recorded)"
    assertions = ", ".join(report.assertion_identity) or "(none)"
    sources = ", ".join(
        sorted({value.split("|")[3] for value in report.mapped_sources if "|" in value})[:3]
    )
    return (
        f"Observed failure family across {size} run(s): earliest divergence on {signals}; "
        f"time characteristics {times}; assertion identity {assertions}"
        + (f"; mapped source(s) {sources}" if sources else "")
        + ". Grouped by family digest from existing evidence; not a root-cause claim."
    )


def _observed_time_range(reports: list[FailureFingerprintReport]) -> list[str]:
    earliest: list[int] = []
    for report in reports:
        for value in report.failure_time_characteristics:
            if value.startswith("earliest="):
                try:
                    earliest.append(int(value.split("=", 1)[1]))
                except ValueError:
                    continue
    if not earliest:
        return []
    low, high = min(earliest), max(earliest)
    if low == high:
        return [f"earliest={low}"]
    return [f"earliest_min={low}", f"earliest_max={high}"]


def _link_families(
    families: list[FailureFamilyGroup],
    representatives: dict[str, FailureFingerprintReport],
) -> list[RelatedFamilyLink]:
    links: list[RelatedFamilyLink] = []
    ordered = sorted(families, key=lambda family: family.family_digest)
    for i, left in enumerate(ordered):
        for right in ordered[i + 1 :]:
            comparison = compare_fingerprint_reports(
                representatives[left.family_digest],
                representatives[right.family_digest],
                left_path=Path(left.representative.source_path),
                right_path=Path(right.representative.source_path),
            )
            if comparison.match_kind != FingerprintMatchKind.RELATED_DIFFERENT:
                continue
            links.append(
                RelatedFamilyLink(
                    family_a_digest=left.family_digest,
                    family_b_digest=right.family_digest,
                    match_kind=str(comparison.match_kind),
                    shared_components=sorted(
                        item.component for item in comparison.component_matches if item.match
                    ),
                    differing_components=sorted(
                        item.component for item in comparison.component_matches if not item.match
                    ),
                )
            )
    return links


def _union(reports: list[FailureFingerprintReport], field: str) -> list[str]:
    values: set[str] = set()
    for report in reports:
        values.update(getattr(report, field))
    return sorted(values)


def _intersection(reports: list[FailureFingerprintReport], field: str) -> list[str]:
    if not reports:
        return []
    common: set[str] = set(getattr(reports[0], field))
    for report in reports[1:]:
        common &= set(getattr(report, field))
    return sorted(common)
