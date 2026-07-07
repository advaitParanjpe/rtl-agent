"""Optional evidence-only LLM supervisor interface.

The supervisor consumes existing structured rtl-agent evidence and asks an
abstract provider for a debug plan. It never executes tools, modifies RTL,
generates patches, or reasons over raw RTL. Without a configured provider it
returns a typed unavailable result, so default workflows need no API key.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from rtl_agent.experiment_comparison_models import ExperimentComparison
from rtl_agent.hkg.memory import HistoricalMemoryResult
from rtl_agent.intervention_ranking_models import InterventionRanking
from rtl_agent.mvp_demo_models import ExperimentOutcome, MvpDemoSummary

SUPERVISOR_SCHEMA_VERSION = 1

SUPERVISOR_EVIDENCE_ONLY_PROMPT = """You are an optional rtl-agent debug supervisor.
Use only the supplied structured evidence. Do not inspect or reason from raw RTL,
Markdown reports, waveform blobs, logs, unstated design intent, or outside facts.
Do not run tools, request automatic tool execution, generate patches, or propose
code edits. Do not claim causality, a root cause, or a proven fix. Describe
recommendations as next evidence checks only, and cite supplied artifact
references for every evidence-backed statement."""

SUPERVISOR_DISCLAIMER = (
    "The supervisor plan is an evidence-only planning aid. It proposes next checks from "
    "supplied structured artifacts, performs no tool execution or patch generation, and "
    "makes no causal/root-cause claim."
)


class ArtifactReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    reference: str


class OutcomeEvidenceSummary(BaseModel):
    intervention_id: str
    observed_effect: str
    rationale: str | None = None
    artifact_dir: str | None = None


class ComparisonEvidenceSummary(BaseModel):
    intervention_id: str
    observed_effect: str
    fingerprint_relation: str | None = None
    comparable: bool
    summary: str
    artifact_dir: str | None = None


class RankingEvidenceSummary(BaseModel):
    intervention_id: str
    rank: int | None = None
    score: int
    ranked: bool
    observed_effect: str
    explanation: str
    evidence_refs: list[str] = Field(default_factory=list)


class MemoryEvidenceSummary(BaseModel):
    seen_before: bool
    canonical_digest: str
    matching_cluster_ids: list[str] = Field(default_factory=list)
    prior_member_failures: list[str] = Field(default_factory=list)
    prior_interventions: list[str] = Field(default_factory=list)
    prior_observed_effects: list[str] = Field(default_factory=list)


class SupervisorEvidence(BaseModel):
    schema_version: int = SUPERVISOR_SCHEMA_VERSION
    demo_id: str | None = None
    command_name: str | None = None
    original_failure_signals: list[str] = Field(default_factory=list)
    observed_effect_counts: dict[str, int] = Field(default_factory=dict)
    outcome_classifications: list[OutcomeEvidenceSummary] = Field(default_factory=list)
    experiment_comparisons: list[ComparisonEvidenceSummary] = Field(default_factory=list)
    intervention_rankings: list[RankingEvidenceSummary] = Field(default_factory=list)
    hkg_memory: MemoryEvidenceSummary | None = None
    artifact_references: list[ArtifactReference] = Field(default_factory=list)
    guardrails: str = SUPERVISOR_EVIDENCE_ONLY_PROMPT


class SupervisorRequest(BaseModel):
    prompt: str
    evidence: SupervisorEvidence


class DebugPlanDraft(BaseModel):
    evidence_summary: list[str] = Field(default_factory=list)
    recommended_next_checks: list[str] = Field(default_factory=list)
    questions_for_engineer: list[str] = Field(default_factory=list)
    risks_uncertainties: list[str] = Field(default_factory=list)
    cited_artifact_references: list[ArtifactReference] = Field(default_factory=list)


class DebugPlan(BaseModel):
    schema_version: int = SUPERVISOR_SCHEMA_VERSION
    status: Literal["available", "unavailable"]
    provider_name: str
    evidence_summary: list[str] = Field(default_factory=list)
    recommended_next_checks: list[str] = Field(default_factory=list)
    questions_for_engineer: list[str] = Field(default_factory=list)
    risks_uncertainties: list[str] = Field(default_factory=list)
    cited_artifact_references: list[ArtifactReference] = Field(default_factory=list)
    prompt_guardrails: str = SUPERVISOR_EVIDENCE_ONLY_PROMPT
    disclaimer: str = SUPERVISOR_DISCLAIMER


class SupervisorProvider(Protocol):
    name: str

    def propose_debug_plan(self, request: SupervisorRequest) -> DebugPlanDraft:
        """Return one structured evidence-only debug plan draft."""


class FakeSupervisorProvider:
    """Deterministic provider for tests and local examples."""

    name = "fake-supervisor"

    def __init__(self) -> None:
        self.requests: list[SupervisorRequest] = []

    def propose_debug_plan(self, request: SupervisorRequest) -> DebugPlanDraft:
        self.requests.append(request)
        evidence = request.evidence
        summary: list[str] = []
        checks: list[str] = []
        questions: list[str] = []
        risks: list[str] = []

        if evidence.observed_effect_counts:
            counts = ", ".join(
                f"{label}={count}"
                for label, count in sorted(evidence.observed_effect_counts.items())
            )
            summary.append(f"Observed-effect counts: {counts}.")
        if evidence.hkg_memory is not None:
            memory = evidence.hkg_memory
            state = "seen before" if memory.seen_before else "not seen before"
            summary.append(
                f"Canonical fingerprint {memory.canonical_digest[:12]} is {state} in HKG memory."
            )
            if memory.matching_cluster_ids:
                checks.append(
                    "Compare this failure against prior cluster(s): "
                    + ", ".join(memory.matching_cluster_ids)
                    + "."
                )
        if evidence.intervention_rankings:
            top = sorted(
                evidence.intervention_rankings,
                key=lambda r: (r.rank is None, r.rank or 0, -r.score, r.intervention_id),
            )[0]
            checks.append(
                f"Review intervention {top.intervention_id} evidence "
                f"(observed_effect={top.observed_effect}, score={top.score})."
            )
        if evidence.outcome_classifications:
            checks.append("Inspect the cited artifacts for the highest-priority observed effects.")
        if not checks:
            checks.append("Collect more structured evidence before asking for a supervised plan.")

        questions.append("Which cited artifact should be inspected first by the engineer?")
        if evidence.hkg_memory is not None and evidence.hkg_memory.seen_before:
            questions.append("Should prior member failures be compared manually against this run?")

        risks.append(
            "Plan is limited to supplied structured evidence and may omit missing artifacts."
        )
        risks.append("Observed effects and historical matches are not causal or root-cause claims.")

        return DebugPlanDraft(
            evidence_summary=summary or ["No structured outcome or memory evidence was supplied."],
            recommended_next_checks=checks,
            questions_for_engineer=questions,
            risks_uncertainties=risks,
            cited_artifact_references=list(evidence.artifact_references),
        )


def build_supervisor_evidence(
    *,
    mvp_summary: MvpDemoSummary | None = None,
    outcome_classifications: list[ExperimentOutcome] | None = None,
    experiment_comparisons: list[ExperimentComparison] | None = None,
    intervention_rankings: list[InterventionRanking] | None = None,
    hkg_memory: HistoricalMemoryResult | None = None,
) -> SupervisorEvidence:
    outcomes = outcome_classifications
    if outcomes is None and mvp_summary is not None:
        outcomes = list(mvp_summary.experiment_outcomes)
    comparisons = experiment_comparisons
    if comparisons is None and mvp_summary is not None:
        comparisons = list(mvp_summary.experiment_comparisons)
    rankings = intervention_rankings
    if rankings is None and mvp_summary is not None:
        rankings = list(mvp_summary.intervention_rankings)

    refs = _artifact_references(
        mvp_summary, outcomes or [], comparisons or [], rankings or [], hkg_memory
    )
    return SupervisorEvidence(
        demo_id=mvp_summary.demo_id if mvp_summary else None,
        command_name=mvp_summary.command_name if mvp_summary else None,
        original_failure_signals=(
            list(mvp_summary.original_failure.earliest_divergence_signals) if mvp_summary else []
        ),
        observed_effect_counts=dict(
            sorted((mvp_summary.observed_effect_counts if mvp_summary else {}).items())
        ),
        outcome_classifications=_outcome_summaries(outcomes or []),
        experiment_comparisons=_comparison_summaries(comparisons or []),
        intervention_rankings=_ranking_summaries(rankings or []),
        hkg_memory=_memory_summary(hkg_memory),
        artifact_references=refs,
    )


def supervise_debug(
    evidence: SupervisorEvidence,
    provider: SupervisorProvider | None = None,
) -> DebugPlan:
    if provider is None:
        return DebugPlan(
            status="unavailable",
            provider_name="none",
            risks_uncertainties=[
                "No supervisor provider is configured; no LLM/API call was made.",
                "Default rtl-agent workflows do not require an API key.",
            ],
            cited_artifact_references=list(evidence.artifact_references),
        )

    request = SupervisorRequest(prompt=SUPERVISOR_EVIDENCE_ONLY_PROMPT, evidence=evidence)
    draft = provider.propose_debug_plan(request)
    return DebugPlan(
        status="available",
        provider_name=provider.name,
        evidence_summary=sorted(dict.fromkeys(draft.evidence_summary)),
        recommended_next_checks=sorted(dict.fromkeys(draft.recommended_next_checks)),
        questions_for_engineer=sorted(dict.fromkeys(draft.questions_for_engineer)),
        risks_uncertainties=sorted(dict.fromkeys(draft.risks_uncertainties)),
        cited_artifact_references=_merge_refs(
            evidence.artifact_references, draft.cited_artifact_references
        ),
    )


def _outcome_summaries(outcomes: list[ExperimentOutcome]) -> list[OutcomeEvidenceSummary]:
    return [
        OutcomeEvidenceSummary(
            intervention_id=o.intervention_id,
            observed_effect=o.observed_effect,
            rationale=o.observed_effect_rationale,
            artifact_dir=o.artifact_dir,
        )
        for o in sorted(outcomes, key=lambda o: o.intervention_id)
    ]


def _comparison_summaries(
    comparisons: list[ExperimentComparison],
) -> list[ComparisonEvidenceSummary]:
    return [
        ComparisonEvidenceSummary(
            intervention_id=c.intervention_id,
            observed_effect=c.observed_effect,
            fingerprint_relation=c.fingerprint.relation,
            comparable=c.comparable,
            summary=c.summary,
            artifact_dir=c.artifact_dir,
        )
        for c in sorted(comparisons, key=lambda c: c.intervention_id)
    ]


def _ranking_summaries(rankings: list[InterventionRanking]) -> list[RankingEvidenceSummary]:
    return [
        RankingEvidenceSummary(
            intervention_id=r.intervention_id,
            rank=r.rank,
            score=r.score,
            ranked=r.ranked,
            observed_effect=r.observed_effect,
            explanation=r.explanation,
            evidence_refs=sorted(r.evidence_refs),
        )
        for r in sorted(rankings, key=lambda r: (r.rank is None, r.rank or 0, r.intervention_id))
    ]


def _memory_summary(memory: HistoricalMemoryResult | None) -> MemoryEvidenceSummary | None:
    if memory is None:
        return None
    return MemoryEvidenceSummary(
        seen_before=memory.seen_before,
        canonical_digest=memory.canonical_digest,
        matching_cluster_ids=list(memory.matching_cluster_ids),
        prior_member_failures=list(memory.prior_member_failures),
        prior_interventions=[item.intervention_id for item in memory.prior_interventions],
        prior_observed_effects=list(memory.prior_observed_effects),
    )


def _artifact_references(
    summary: MvpDemoSummary | None,
    outcomes: list[ExperimentOutcome],
    comparisons: list[ExperimentComparison],
    rankings: list[InterventionRanking],
    memory: HistoricalMemoryResult | None,
) -> list[ArtifactReference]:
    refs: list[ArtifactReference] = []
    if summary is not None:
        for ref in summary.evidence_references:
            refs.append(ArtifactReference(name=ref.name, reference=ref.path))
        for stage in summary.stages:
            if stage.reference:
                refs.append(
                    ArtifactReference(name=f"stage:{stage.stage}", reference=stage.reference)
                )
    for outcome in outcomes:
        if outcome.artifact_dir:
            refs.append(
                ArtifactReference(
                    name=f"outcome:{outcome.intervention_id}", reference=outcome.artifact_dir
                )
            )
    for comparison in comparisons:
        if comparison.artifact_dir:
            refs.append(
                ArtifactReference(
                    name=f"comparison:{comparison.intervention_id}",
                    reference=comparison.artifact_dir,
                )
            )
    for ranking in rankings:
        for evidence_ref in ranking.evidence_refs:
            refs.append(
                ArtifactReference(
                    name=f"ranking:{ranking.intervention_id}",
                    reference=evidence_ref,
                )
            )
    if memory is not None:
        for prov in memory.provenance:
            refs.append(
                ArtifactReference(
                    name=f"memory:{prov.artifact_id}",
                    reference=prov.path or prov.content_sha256 or prov.artifact_id,
                )
            )
    return _merge_refs(refs)


def _merge_refs(*groups: list[ArtifactReference]) -> list[ArtifactReference]:
    merged: dict[tuple[str, str], ArtifactReference] = {}
    for group in groups:
        for ref in group:
            merged.setdefault((ref.name, ref.reference), ref)
    return [merged[key] for key in sorted(merged)]
