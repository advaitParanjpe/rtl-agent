from __future__ import annotations

from pathlib import Path

from rtl_agent.intervention_template_models import InterventionCandidate, InterventionTemplateReport


def write_template_report(report: InterventionTemplateReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")


def render_template_markdown(report: InterventionTemplateReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_markdown(report), encoding="utf-8")


def _markdown(report: InterventionTemplateReport) -> str:
    lines = [
        f"# Generated intervention candidates `{report.generation_id}`",
        "",
        f"- Failure run: `{report.failure_run}`",
        f"- Target repository: `{report.target_repo}`",
        f"- Target commit: `{report.target_commit}`",
        f"- Baseline family digest: `{(report.baseline_family_digest or '-')[:16]}`",
        f"- Earliest divergence time: {report.earliest_divergence_time}",
        f"- Allowed files: {', '.join(f'`{f}`' for f in report.allowed_files)}",
        f"- Maximum candidates: {report.max_candidates}",
        "",
        "These candidates are experiment proposals for the experiment matrix, not fixes or "
        "causal conclusions. Feed `interventions.json` directly to `rtl-agent "
        "run-experiment-matrix`.",
        "",
        "## Candidates",
        "",
    ]
    if not report.candidates:
        lines.append("_No candidate met the evidence bar for a bounded, unambiguous edit._")
        lines.append("")
    for candidate in report.candidates:
        lines.extend(_candidate_block(candidate))

    summary = report.summary
    lines += [
        "## Summary",
        "",
        f"- Templates considered: {summary.templates_considered}",
        f"- Candidates emitted: {summary.candidates_emitted}",
        f"- Sites skipped: {summary.sites_skipped}",
        f"- High evidence: {summary.high_evidence}",
        f"- Moderate evidence: {summary.moderate_evidence}",
        f"- Low evidence: {summary.low_evidence}",
        "",
    ]
    if report.unsupported:
        lines += ["## Unsupported templates", ""]
        for item in report.unsupported:
            lines.append(f"- `{item.template_kind}` — {item.reason}")
        lines.append("")
    if report.skipped:
        lines += ["## Skipped sites", ""]
        for site in report.skipped:
            where = f" at `{site.location}`" if site.location else ""
            signal = f" (`{site.signal}`)" if site.signal else ""
            lines.append(f"- `{site.template_kind}`{signal}{where} — {site.reason}")
        lines.append("")
    lines += ["## Disclaimer", "", report.disclaimer, ""]
    return "\n".join(lines)


def _candidate_block(candidate: InterventionCandidate) -> list[str]:
    ev = candidate.evidence
    chain = (
        f"signal `{ev.leaf}` (mapping {ev.mapping_status}"
        + (f", divergence node `{ev.divergence_node}`" if ev.divergence_node else "")
        + (f" @ t={ev.divergence_time}" if ev.divergence_time is not None else "")
        + (
            f", failing=`{ev.failing_value}` passing=`{ev.passing_value}`"
            if ev.failing_value
            else ""
        )
        + ")"
    )
    drivers = "; ".join(
        f"{d.statement_kind} `{d.statement_text}` at {d.file_path}:{d.line}"
        + (f" guard `{d.guard}`" if d.guard else "")
        for d in ev.drivers
    )
    return [
        f"### `{candidate.candidate_id}`",
        "",
        f"- Hypothesis: {candidate.hypothesis}",
        f"- Intervention type: `{candidate.template_kind}`",
        f"- Confidence: `{candidate.confidence}`",
        f"- Source location: `{candidate.file}:{candidate.source_line}`",
        f"- Affected signal: `{candidate.affected_signal}`"
        + (
            f" | condition: `{candidate.affected_condition}`"
            if candidate.affected_condition
            else ""
        ),
        "- Original code:",
        "",
        "```systemverilog",
        candidate.replace_old,
        "```",
        "- Proposed code:",
        "",
        "```systemverilog",
        candidate.proposed_replacement,
        "```",
        f"- Evidence chain: {chain}; drivers: {drivers}",
        f"- Warnings: {', '.join(candidate.warnings) if candidate.warnings else 'none'}",
        "- Experiment-matrix compatible: yes (emitted in `interventions.json`).",
        f"- Note: {candidate.experiment_note}",
        "",
    ]
