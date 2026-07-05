from __future__ import annotations

import json
from pathlib import Path

from rtl_agent.failure_family_models import FailureFamilyClusterReport


def write_family_report(report: FailureFamilyClusterReport, output: Path) -> None:
    if output.exists() and output.is_dir():
        raise ValueError(f"output path is a directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def render_family_markdown(report: FailureFamilyClusterReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_markdown(report), encoding="utf-8")


def _markdown(report: FailureFamilyClusterReport) -> str:
    summary = report.input_summary
    lines: list[str] = []
    lines.append("# Regression Failure-Family Report")
    lines.append("")
    lines.append(
        "_Deterministic, read-only grouping of existing failure fingerprints by observed "
        "failure mechanism. Families are not root-cause claims._"
    )
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- strictness: `{summary.strictness}`")
    lines.append(f"- total inputs: {summary.total_inputs}")
    lines.append(f"- valid fingerprints: {summary.valid_fingerprints}")
    lines.append(f"- families: {summary.family_count}")
    lines.append(f"- exact duplicates: {summary.exact_duplicate_count}")
    lines.append(f"- unique outliers: {summary.outlier_count}")
    lines.append(f"- insufficient evidence: {summary.insufficient_evidence_count}")
    lines.append(f"- excluded inputs: {summary.excluded_invalid}")
    lines.append("")

    if report.families:
        lines.append("## Failure families")
        for index, family in enumerate(report.families, start=1):
            outlier = " (unique outlier)" if family.is_outlier else ""
            lines.append(f"### Family {index}{outlier} — `{family.family_digest[:12]}`")
            lines.append(f"- size: {family.size}")
            lines.append(f"- {family.description}")
            lines.append(
                f"- representative: `{family.representative.source_path}` "
                f"({family.representative.selection_reason})"
            )
            if family.observed_time_range:
                lines.append(f"- observed time range: {', '.join(family.observed_time_range)}")
            if family.earliest_divergent_signals_union:
                lines.append(
                    "- earliest divergent signals: "
                    + ", ".join(family.earliest_divergent_signals_union)
                )
            if family.assertion_identities:
                lines.append(f"- assertion identities: {', '.join(family.assertion_identities)}")
            duplicates = [g for g in family.exact_duplicate_subgroups if g.size > 1]
            if duplicates:
                lines.append(
                    "- exact-duplicate subgroups: "
                    + ", ".join(f"{g.exact_digest[:12]}×{g.size}" for g in duplicates)
                )
            lines.append("")

    if report.related_family_links:
        lines.append("## Related families")
        for link in report.related_family_links:
            lines.append(
                f"- `{link.family_a_digest[:12]}` ↔ `{link.family_b_digest[:12]}`: "
                f"{link.match_kind} (shared: {', '.join(link.shared_components) or 'none'})"
            )
        lines.append("")

    if report.insufficient_evidence:
        lines.append("## Insufficient-evidence fingerprints")
        for entry in report.insufficient_evidence:
            lines.append(f"- `{entry.source_path}`: {', '.join(entry.reasons)}")
        lines.append("")

    if report.excluded_inputs:
        lines.append("## Excluded inputs")
        for excluded in report.excluded_inputs:
            lines.append(f"- `{excluded.source_path}`: {excluded.reason}")
        lines.append("")

    if report.warnings:
        lines.append("## Warnings")
        for warning in report.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    return "\n".join(lines) + "\n"
