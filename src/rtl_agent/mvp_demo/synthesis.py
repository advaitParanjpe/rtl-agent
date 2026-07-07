"""Deterministic synthesis of the MVP demo outputs into a debug summary.

This layer reorganizes the already-computed MVP demo summary (original failure,
minimized stimulus, generated candidates, and classified experiment outcomes)
into a coherent, evidence-backed debug summary: observed effects grouped by
label, consolidated evidence references, and concise next-debug checks derived
only from the observed labels. It runs no new analysis, and every suggestion is
an observation about what to inspect next — never a causal or root-cause claim.
"""

from __future__ import annotations

from rtl_agent.mvp_demo_models import (
    CandidateSummary,
    EvidenceReference,
    ExperimentOutcome,
    MinimizationSummary,
    MvpDemoSummary,
    NextDebugCheck,
    NotableEffectGroup,
    OriginalFailure,
    StageRef,
)

# Deterministic display order for observed-effect labels (most actionable first).
LABEL_ORDER = [
    "failure_removed",
    "failure_changed",
    "new_failure",
    "failure_delayed",
    "failure_advanced",
    "no_observable_effect",
    "experiment_invalid",
    "unknown",
]

_LABEL_SUMMARY = {
    "failure_removed": "the observed failure no longer reproduced when the edit was applied",
    "failure_changed": "the same failing signal produced a materially different failure family",
    "new_failure": "a divergence appeared on a different signal than the original failure",
    "failure_delayed": "the same failure family reproduced later in time",
    "failure_advanced": "the same failure family reproduced earlier in time",
    "no_observable_effect": "no observable change in the failure was measured",
    "experiment_invalid": "the experiment did not produce a comparable observation",
    "unknown": "the observed effect could not be classified from the available evidence",
}


def build_notable_effects(outcomes: list[ExperimentOutcome]) -> list[NotableEffectGroup]:
    by_label: dict[str, list[str]] = {}
    for outcome in outcomes:
        by_label.setdefault(outcome.observed_effect, []).append(outcome.intervention_id)
    groups: list[NotableEffectGroup] = []
    ordered_labels = [label for label in LABEL_ORDER if label in by_label]
    ordered_labels += sorted(label for label in by_label if label not in LABEL_ORDER)
    for label in ordered_labels:
        interventions = sorted(by_label[label])
        groups.append(
            NotableEffectGroup(
                label=label,
                count=len(interventions),
                summary=_LABEL_SUMMARY.get(label, "observed effect"),
                interventions=interventions,
            )
        )
    return groups


def build_evidence_references(
    stages: list[StageRef],
    original: OriginalFailure,
    minimization: MinimizationSummary,
    outcomes: list[ExperimentOutcome],
) -> list[EvidenceReference]:
    references: list[EvidenceReference] = [
        EvidenceReference(name="failure_run", path=original.failure_run),
    ]
    if original.failure_package:
        references.append(EvidenceReference(name="failure_package", path=original.failure_package))
    references.append(
        EvidenceReference(name="reduction_report", path=minimization.reduction_report)
    )
    for stage in stages:
        if stage.stage in {"generate-interventions", "run-experiment-matrix"} and stage.reference:
            references.append(EvidenceReference(name=stage.stage, path=stage.reference))
    for outcome in outcomes:
        if outcome.artifact_dir:
            references.append(
                EvidenceReference(
                    name=f"experiment:{outcome.intervention_id}", path=outcome.artifact_dir
                )
            )
    return references


def build_next_debug_checks(
    minimization: MinimizationSummary,
    outcomes: list[ExperimentOutcome],
    candidates: list[CandidateSummary],
) -> list[NextDebugCheck]:
    location_by_id = {c.candidate_id: f"{c.file}:{c.source_line}" for c in candidates}
    by_label: dict[str, list[str]] = {}
    for outcome in outcomes:
        by_label.setdefault(outcome.observed_effect, []).append(outcome.intervention_id)

    checks: list[str] = []
    basis: list[str] = []

    def sites(ids: list[str]) -> str:
        return ", ".join(
            f"`{i}` ({location_by_id[i]})" if i in location_by_id else f"`{i}`" for i in sorted(ids)
        )

    if by_label.get("failure_removed"):
        checks.append(
            f"Inspect the edit sites exercised by {sites(by_label['failure_removed'])} first — "
            "the observed failure did not reproduce when those edits were applied."
        )
        basis.append("failure_removed experiments")
    if by_label.get("failure_changed"):
        checks.append(
            f"Compare the result fingerprints of {sites(by_label['failure_changed'])} against the "
            "original family to characterize how the observed failure changed."
        )
        basis.append("failure_changed experiments")
    if by_label.get("new_failure"):
        checks.append(
            f"Check whether {sites(by_label['new_failure'])} expose a separate issue — they "
            "produced a divergence on a different signal than the original failure."
        )
        basis.append("new_failure experiments")
    timing = sorted(by_label.get("failure_delayed", []) + by_label.get("failure_advanced", []))
    if timing:
        checks.append(
            f"Re-examine timing around {sites(timing)} — the same failure family reproduced at a "
            "shifted time."
        )
        basis.append("failure_delayed/advanced experiments")
    if by_label.get("experiment_invalid"):
        checks.append(
            f"Re-run or repair the experiments that did not complete "
            f"({sites(by_label['experiment_invalid'])}) before drawing conclusions from them."
        )
        basis.append("experiment_invalid experiments")
    if by_label.get("unknown"):
        checks.append(
            f"Manually review {sites(by_label['unknown'])} — their observed effect could not be "
            "classified from the available evidence."
        )
        basis.append("unknown experiments")
    if not (
        by_label.get("failure_removed")
        or by_label.get("failure_changed")
        or by_label.get("new_failure")
    ):
        checks.append(
            "No generated edit altered the observed failure; consider widening the allowed files "
            "or increasing the candidate budget before further experiments."
        )
        basis.append("no altering experiment observed")

    checks.append(
        f"Use the minimized {minimization.minimized_item_count}-item stimulus "
        f"(`{minimization.reduction_report}`) as the compact reproducer for further debugging."
    )
    basis.append("minimized counterexample")

    return [
        NextDebugCheck(priority=i + 1, statement=text, basis=basis[i])
        for i, text in enumerate(checks)
    ]


def render_debug_summary(summary: MvpDemoSummary) -> str:
    of = summary.original_failure
    mn = summary.minimization
    lines = [
        f"# Counterfactual debug summary `{summary.demo_id}`",
        "",
        "An evidence-guided counterfactual investigation of one observed failure. Each result "
        "below is an observed experimental effect of a bounded, reviewable edit; nothing here is "
        "a proven fix or a statement of cause.",
        "",
        f"- Target repository: `{summary.target_repo}`",
        f"- Target commit: `{summary.target_commit}`",
        f"- Command: `{summary.command_name}`",
        "",
        "## Original failure",
        "",
        f"- Observed failure family: `{(of.family_digest or '-')[:16]}`",
        f"- Earliest divergence: {of.earliest_divergence_signals or '-'} "
        f"at t={of.earliest_divergence_time}",
        f"- Failure run: `{of.failure_run}` (valid: {of.run_valid})",
        f"- Portable failure package: `{of.failure_package}` ({of.failure_package_files} files)",
        "",
        "## Minimized stimulus",
        "",
        f"- Reduced {mn.original_item_count} → {mn.minimized_item_count} items "
        f"({mn.percent_reduced}% smaller), classification `{mn.final_classification}`",
        f"- Minimized-stimulus digest: `{mn.minimized_stimulus_digest[:16]}`",
        "",
        "## Generated interventions",
        "",
        f"- {len(summary.generated_candidates)} reviewable candidate(s); "
        + (", ".join(f"{k}={v}" for k, v in sorted(summary.candidate_counts.items())) or "none"),
        "",
        "## Outcome classification",
        "",
    ]
    if summary.observed_effect_counts:
        lines += [
            f"- `{label}`: {count}"
            for label, count in _ordered_counts(summary.observed_effect_counts)
        ]
    else:
        lines.append("- (no experiments were run)")
    lines += ["", "## Notable observed effects", ""]
    if summary.notable_effects:
        for group in summary.notable_effects:
            lines.append(f"### `{group.label}` ({group.count}) — {group.summary}")
            for outcome in _outcomes_for(summary, group.interventions):
                where = f" at `{_location(summary, outcome.intervention_id)}`"
                lines.append(
                    f"- `{outcome.intervention_id}` ({outcome.template_kind}, "
                    f"{outcome.confidence}){where}: {outcome.observed_effect_rationale or '-'}"
                )
            lines.append("")
    else:
        lines += ["_No experiments were classified._", ""]

    lines += ["## Intervention ranking", ""]
    if summary.intervention_rankings:
        lines += [
            "Most informative counterfactuals first, scored deterministically from observed "
            "evidence only (no causal claim).",
            "",
            "| Rank | Intervention | Score | Observed effect | Result cluster | Why |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for r in summary.intervention_rankings:
            rank = str(r.rank) if r.rank is not None else "—"
            cluster = (
                f"{r.result_cluster_id} (n={r.result_cluster_size})" if r.result_cluster_id else "-"
            )
            why = r.explanation if r.ranked else (r.unranked_reason or "unranked")
            lines.append(
                f"| {rank} | `{r.intervention_id}` | {r.score} | **{r.observed_effect}** "
                f"| {cluster} | {why} |"
            )
        lines.append("")
    else:
        lines += ["_No experiments to rank._", ""]

    lines += ["## Result comparisons", ""]
    if summary.experiment_comparisons:
        lines += [
            "Each experiment compared against the original failure (reproduced on the minimized "
            "counterexample).",
            "",
            "| Experiment | Observed effect | Fingerprint (exact/family/canonical) "
            "| Δt | Signals (shared/+/-) | Summary |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for cmp in summary.experiment_comparisons:
            fp = cmp.fingerprint
            fp_cell = f"{_yn(fp.exact_match)}/{_yn(fp.family_match)}/{_yn(fp.canonical_match)}"
            delta = (
                f"{cmp.earliest_divergence_time_change:+d}"
                if cmp.earliest_divergence_time_change is not None
                else "-"
            )
            sig = cmp.signal_change
            signals = f"{sig.shared or '[]'} / {sig.added or '[]'} / {sig.removed or '[]'}"
            lines.append(
                f"| `{cmp.intervention_id}` | **{cmp.observed_effect}** | {fp_cell} | {delta} "
                f"| {signals} | {cmp.summary} |"
            )
        lines.append("")
    else:
        lines += ["_No experiments to compare._", ""]

    lines += ["## Repair-direction suggestions", ""]
    if summary.repair_suggestions:
        lines += [
            "Deterministic areas to inspect from observed counterfactual evidence only; these are "
            "not patches or root-cause claims.",
            "",
        ]
        for suggestion in summary.repair_suggestions:
            lines.append(f"### `{suggestion.suggestion_id}` — {suggestion.confidence}")
            lines.append(f"- Suggested area: {suggestion.suggested_area}")
            if suggestion.related_source_locations:
                lines.append(
                    "- Related source locations: "
                    + ", ".join(f"`{loc}`" for loc in suggestion.related_source_locations)
                )
            if suggestion.related_signals:
                lines.append(
                    "- Related signals: "
                    + ", ".join(f"`{signal}`" for signal in suggestion.related_signals)
                )
            lines.append(
                "- Supporting interventions/outcomes: "
                + ", ".join(f"`{i}`" for i in suggestion.supporting_interventions)
                + " / "
                + ", ".join(f"`{o}`" for o in suggestion.supporting_outcomes)
            )
            for basis in suggestion.evidence_basis:
                lines.append(f"- Evidence: {basis}")
            lines.append(f"- Disclaimer: {suggestion.disclaimer}")
            lines.append("")
    else:
        lines += [
            "_No repair-direction suggestions were generated from the available evidence._",
            "",
        ]

    lines += ["## Evidence references", ""]
    for ref in summary.evidence_references:
        lines.append(f"- {ref.name}: `{ref.path}`")
    lines += ["", "## Next debug checks", ""]
    for check in summary.next_debug_checks:
        lines.append(f"{check.priority}. {check.statement}")
    lines += ["", "## Disclaimer", "", summary.disclaimer, ""]
    return "\n".join(lines)


def _yn(value: bool) -> str:
    return "yes" if value else "no"


def _ordered_counts(counts: dict[str, int]) -> list[tuple[str, int]]:
    ordered = [(label, counts[label]) for label in LABEL_ORDER if label in counts]
    ordered += sorted((k, v) for k, v in counts.items() if k not in LABEL_ORDER)
    return ordered


def _outcomes_for(summary: MvpDemoSummary, ids: list[str]) -> list[ExperimentOutcome]:
    by_id = {o.intervention_id: o for o in summary.experiment_outcomes}
    return [by_id[i] for i in ids if i in by_id]


def _location(summary: MvpDemoSummary, intervention_id: str) -> str:
    for candidate in summary.generated_candidates:
        if candidate.candidate_id == intervention_id:
            return f"{candidate.file}:{candidate.source_line}"
    return intervention_id
