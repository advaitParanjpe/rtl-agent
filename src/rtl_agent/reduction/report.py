from __future__ import annotations

import json
from pathlib import Path

from rtl_agent.reduction_models import StimulusReductionReport


def write_reduction_report(report: StimulusReductionReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def render_reduction_markdown(report: StimulusReductionReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_markdown(report), encoding="utf-8")


def _percentage_reduced(report: StimulusReductionReport) -> int:
    if report.original_item_count == 0:
        return 0
    removed = report.original_item_count - report.minimized_item_count
    return round(100 * removed / report.original_item_count)


def _markdown(report: StimulusReductionReport) -> str:
    lines: list[str] = []
    lines.append("# Stimulus Minimization Report")
    lines.append("")
    lines.append(f"_{report.disclaimer}_")
    lines.append("")
    lines.append(f"- **Final classification:** `{report.final_classification}`")
    lines.append(f"- **Termination:** `{report.termination_reason}`")
    lines.append(
        f"- **Items:** {report.original_item_count} -> {report.minimized_item_count} "
        f"({_percentage_reduced(report)}% reduced)"
    )
    lines.append(f"- **Evaluations:** {report.total_evaluations} (cache hits {report.cache_hits})")
    lines.append(f"- **Evaluation budget:** {report.evaluation_budget}")
    lines.append(f"- **Baseline family digest:** `{report.baseline_fingerprint_family_digest}`")
    lines.append(f"- **Target commit:** {report.target_commit or 'unknown'}")
    lines.append("")

    lines.append("## Minimized stimulus")
    lines.append(f"- retained items: {', '.join(report.retained_item_ids) or '(none)'}")
    lines.append(f"- removed items: {', '.join(report.removed_item_ids) or '(none)'}")
    lines.append(f"- minimized digest: `{report.minimized_stimulus_digest}`")
    lines.append("")

    if report.simulator_result is not None:
        lines.append("## Simulator")
        lines.append(
            f"- command `{report.simulator_result.command_name}` -> "
            f"`{report.simulator_result.status}` (exit {report.simulator_result.exit_code}, "
            f"timeout {report.simulator_result.timeout_seconds}s)"
        )
        lines.append("")

    lines.append("## Evaluation history")
    for index, evaluation in enumerate(report.evaluation_history, start=1):
        cache = " (cache)" if evaluation.from_cache else ""
        lines.append(
            f"{index}. `{evaluation.candidate_digest[:12]}` "
            f"({evaluation.item_count} items) -> `{evaluation.classification}`{cache}"
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

    lines.append("## Reproducibility")
    for instruction in report.reproducibility_instructions:
        lines.append(f"- {instruction}")
    lines.append("")

    return "\n".join(lines) + "\n"
