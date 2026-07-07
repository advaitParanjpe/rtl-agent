from __future__ import annotations

import json
from pathlib import Path

from rtl_agent.experiment_matrix_models import ExperimentMatrixReport, MatrixRow


def write_matrix_report(report: ExperimentMatrixReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def render_matrix_markdown(report: ExperimentMatrixReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_markdown(report), encoding="utf-8")


def _markdown(report: ExperimentMatrixReport) -> str:
    lines = [
        f"# Experiment matrix `{report.matrix_id}`",
        "",
        f"- Baseline run: `{report.baseline_run}`",
        f"- Baseline family digest: `{report.baseline_family_digest[:16]}`",
        f"- Target repository: `{report.target_repo}`",
        f"- Target commit: `{report.target_commit}`",
        f"- Command: `{report.command_name}`",
        f"- Minimized stimulus digest: `{report.minimized_stimulus_digest[:16]}`",
        f"- Reduction report: `{report.reduction_report}`",
        f"- Maximum experiments: {report.max_experiments}",
        "",
        "## Outcome matrix",
        "",
        "| Intervention | State | Counterfactual | Fingerprint | Family | Δtime | Artifacts |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report.rows:
        lines.append(_row_line(row))

    summary = report.summary
    lines += [
        "",
        "## Summary",
        "",
        f"- Requested: {summary.total_requested}",
        f"- Executed: {summary.executed}",
        f"- Skipped: {summary.skipped}",
        f"- Cache hits: {summary.cache_hits}",
        f"- Failures removed: {summary.failures_removed}",
        f"- Same-family outcomes: {summary.same_family}",
        f"- Changed-family outcomes: {summary.changed_family}",
        f"- No-effect outcomes: {summary.no_effect}",
        f"- Infrastructure failures: {summary.infrastructure_failures}",
        f"- Insufficient-evidence outcomes: {summary.insufficient_evidence}",
        "",
    ]
    if report.warnings:
        lines += ["## Warnings", ""]
        lines += [f"- {warning}" for warning in report.warnings]
        lines.append("")
    lines += ["## Disclaimer", "", report.disclaimer, ""]
    return "\n".join(lines)


def _row_line(row: MatrixRow) -> str:
    family = row.result_family_digest[:12] if row.result_family_digest else "-"
    delta = "-"
    if row.result_failure_time is not None and row.baseline_failure_time is not None:
        delta = f"{row.result_failure_time - row.baseline_failure_time:+d}"
    artifacts = row.artifact_dir or "-"
    cache = " (cache)" if row.from_cache else ""
    return (
        f"| `{row.intervention_id}`{cache} | {row.execution_status} "
        f"| {row.counterfactual_outcome or '-'} | {row.fingerprint_relation or '-'} "
        f"| `{family}` | {delta} | `{artifacts}` |"
    )
