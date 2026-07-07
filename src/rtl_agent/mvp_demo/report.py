from __future__ import annotations

from pathlib import Path

from rtl_agent.mvp_demo_models import MvpDemoSummary


def write_demo_summary(summary: MvpDemoSummary, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(summary.model_dump_json(indent=2) + "\n", encoding="utf-8")


def render_demo_markdown(summary: MvpDemoSummary, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_markdown(summary), encoding="utf-8")


def _markdown(summary: MvpDemoSummary) -> str:
    of = summary.original_failure
    mn = summary.minimization
    lines = [
        f"# Evidence-guided counterfactual demonstration `{summary.demo_id}`",
        "",
        f"- Target repository: `{summary.target_repo}`",
        f"- Target commit: `{summary.target_commit}`",
        f"- Command: `{summary.command_name}`",
        "",
        "## Workflow stages",
        "",
        "| Stage | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for stage in summary.stages:
        lines.append(f"| `{stage.stage}` | {stage.status} | {stage.detail or ''} |")

    lines += [
        "",
        "## 1. Original failure",
        "",
        f"- Failure run: `{of.failure_run}` (valid: {of.run_valid})",
        f"- Observed failure family: `{(of.family_digest or '-')[:16]}`",
        f"- Earliest divergence: {of.earliest_divergence_signals} "
        f"at t={of.earliest_divergence_time}",
        f"- Portable failure package: `{of.failure_package}` ({of.failure_package_files} files)",
        "",
        "### Minimized counterexample",
        "",
        f"- {mn.original_item_count} → {mn.minimized_item_count} stimulus items "
        f"({mn.percent_reduced}% reduced), classification `{mn.final_classification}`",
        f"- Reduction report: `{mn.reduction_report}`",
        "",
        "## 2. Generated intervention candidates",
        "",
    ]
    if summary.generated_candidates:
        lines += [
            "| Candidate | Kind | Confidence | Location | Hypothesis |",
            "| --- | --- | --- | --- | --- |",
        ]
        for c in summary.generated_candidates:
            lines.append(
                f"| `{c.candidate_id}` | {c.template_kind} | {c.confidence} | "
                f"`{c.file}:{c.source_line}` | {c.hypothesis} |"
            )
        lines.append("")
        lines.append(
            "Candidate confidence counts: "
            + ", ".join(f"{k}={v}" for k, v in sorted(summary.candidate_counts.items()))
        )
    else:
        lines.append("_No reviewable candidate met the evidence bar._")
    lines.append("")

    lines += ["## 3. Experiment outcomes", ""]
    if summary.experiment_outcomes:
        lines += [
            "| Experiment | Kind | Status | Observed effect | Fingerprint | Rationale |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for o in summary.experiment_outcomes:
            lines.append(
                f"| `{o.intervention_id}` | {o.template_kind or '-'} | {o.execution_status} | "
                f"**{o.observed_effect}** | {o.fingerprint_relation or '-'} | "
                f"{o.observed_effect_rationale or '-'} |"
            )
        lines.append("")
        lines.append(
            "Observed-effect labels: "
            + ", ".join(f"{k}={v}" for k, v in sorted(summary.observed_effect_counts.items()))
        )
    else:
        lines.append("_No experiments were run._")
    lines.append("")

    lines += ["## 4. Evidence-backed observations", ""]
    for obs in summary.observations:
        prefix = f"(`{obs.intervention_id}`) " if obs.intervention_id else ""
        lines.append(f"- [{obs.category}] {prefix}{obs.statement}")
    lines.append("")

    if summary.warnings:
        lines += ["## Warnings", ""]
        lines += [f"- {w}" for w in summary.warnings]
        lines.append("")

    lines += ["## Disclaimer", "", summary.disclaimer, ""]
    return "\n".join(lines)
