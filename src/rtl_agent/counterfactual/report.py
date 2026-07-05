from __future__ import annotations

import json
from pathlib import Path

from rtl_agent.counterfactual_models import CounterfactualExperimentReport


def write_experiment_report(report: CounterfactualExperimentReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def render_experiment_markdown(report: CounterfactualExperimentReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_markdown(report), encoding="utf-8")


def _markdown(report: CounterfactualExperimentReport) -> str:
    lines: list[str] = []
    lines.append("# Counterfactual Experiment Report")
    lines.append("")
    lines.append(f"_{report.disclaimer}_")
    lines.append("")
    lines.append(f"- **Outcome:** `{report.outcome}`")
    lines.append(f"- **Experiment:** {report.experiment_id}")
    lines.append(f"- **Target repository:** {report.target_repo}")
    lines.append(f"- **Baseline commit:** {report.baseline_commit or 'unknown'}")
    lines.append(
        f"- **Intervention:** {report.intervention.kind} (applied={report.intervention.applied})"
    )
    if report.intervention.target_files:
        lines.append(f"- **Intervention files:** {', '.join(report.intervention.target_files)}")
    lines.append(f"- **Allowed files:** {', '.join(report.intervention.allowed_files)}")
    lines.append("")

    lines.append("## Baseline failure")
    lines.append(
        f"- signals: {', '.join(report.baseline_failure.signals) or '(none)'}; "
        f"time: {report.baseline_failure.failure_time}"
    )
    if report.baseline_failure.fingerprint_exact_digest:
        lines.append(
            f"- fingerprint: `{report.baseline_failure.fingerprint_exact_digest}` "
            f"(family `{report.baseline_failure.fingerprint_family_digest}`)"
        )
    lines.append("")
    lines.append("## Intervention-run failure")
    lines.append(
        f"- signals: {', '.join(report.intervention_failure.signals) or '(none)'}; "
        f"time: {report.intervention_failure.failure_time}"
    )
    if report.intervention_failure.assertion_label:
        lines.append(
            f"- assertion: {report.intervention_failure.assertion_label} "
            f"@ {report.intervention_failure.assertion_time}"
        )
    if report.intervention_failure.fingerprint_exact_digest:
        lines.append(
            f"- fingerprint: `{report.intervention_failure.fingerprint_exact_digest}` "
            f"(family `{report.intervention_failure.fingerprint_family_digest}`)"
        )
    lines.append("")

    if report.execution is not None:
        lines.append("## Execution")
        lines.append(
            f"- command `{report.execution.command_name}` -> status "
            f"`{report.execution.status}` (exit {report.execution.exit_code})"
        )
        if report.execution.waveform_references:
            lines.append(
                f"- waveform references: {', '.join(report.execution.waveform_references)}"
            )
        lines.append("")

    if report.observable_differences:
        lines.append("## Observable differences")
        for difference in report.observable_differences:
            lines.append(
                f"- {difference.field}: baseline `{difference.baseline}` -> "
                f"intervention `{difference.intervention}`"
            )
        lines.append("")

    if report.insufficient_evidence_reasons:
        lines.append("## Evidence gaps")
        for reason in report.insufficient_evidence_reasons:
            lines.append(f"- {reason}")
        lines.append("")

    if report.warnings:
        lines.append("## Warnings")
        for warning in report.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    return "\n".join(lines) + "\n"
