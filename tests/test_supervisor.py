from __future__ import annotations

from datetime import UTC, datetime

from rtl_agent.experiment_comparison_models import (
    ExperimentComparison,
    FingerprintRelationship,
    SignalChange,
)
from rtl_agent.hkg import HistoricalMemoryResult, PriorInterventionSummary, Provenance
from rtl_agent.intervention_ranking_models import InterventionRanking, RankingFactor
from rtl_agent.mvp_demo_models import (
    EvidenceReference,
    ExperimentOutcome,
    MinimizationSummary,
    MvpDemoSummary,
    OriginalFailure,
    StageRef,
)
from rtl_agent.supervisor import (
    SUPERVISOR_EVIDENCE_ONLY_PROMPT,
    ArtifactReference,
    DebugPlanDraft,
    FakeSupervisorProvider,
    SupervisorRequest,
    build_supervisor_evidence,
    supervise_debug,
)


def _summary() -> MvpDemoSummary:
    outcome = ExperimentOutcome(
        intervention_id="cand-a",
        template_kind="hold_register",
        confidence="high_evidence",
        execution_status="executed",
        observed_effect="failure_removed",
        observed_effect_rationale="no reproduced divergence in cited experiment",
        artifact_dir="/demo/matrix/cand-a",
    )
    comparison = ExperimentComparison(
        intervention_id="cand-a",
        template_kind="hold_register",
        confidence="high_evidence",
        execution_status="executed",
        comparable=False,
        observed_effect="failure_removed",
        fingerprint=FingerprintRelationship(relation="removed"),
        signal_change=SignalChange(removed=["hold"]),
        artifact_dir="/demo/matrix/cand-a",
        summary="The failure no longer reproduced; no result fingerprint was compared.",
    )
    ranking = InterventionRanking(
        intervention_id="cand-a",
        template_kind="hold_register",
        confidence="high_evidence",
        rank=1,
        score=116,
        ranked=True,
        observed_effect="failure_removed",
        result_cluster_id="cluster-x",
        factors=[RankingFactor(factor="observed_effect:failure_removed", points=100)],
        explanation="Observed failure removal and high evidence confidence.",
        evidence_refs=["/demo/matrix/cand-a"],
    )
    return MvpDemoSummary(
        demo_id="demo",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        target_repo="/repo",
        command_name="sim",
        stages=[
            StageRef(stage="inspect-run", status="valid", reference="/demo/run"),
            StageRef(stage="run-experiment-matrix", status="executed", reference="/demo/matrix"),
        ],
        original_failure=OriginalFailure(
            failure_run="/demo/run",
            run_valid=True,
            earliest_divergence_time=40,
            earliest_divergence_signals=["hold"],
        ),
        minimization=MinimizationSummary(
            reduction_report="/demo/reduction.json",
            original_item_count=5,
            minimized_item_count=2,
            percent_reduced=60,
            final_classification="same_failure_family",
            minimized_stimulus_digest="d" * 64,
        ),
        experiment_outcomes=[outcome],
        experiment_comparisons=[comparison],
        intervention_rankings=[ranking],
        observed_effect_counts={"failure_removed": 1},
        evidence_references=[EvidenceReference(name="matrix", path="/demo/matrix")],
    )


def _memory() -> HistoricalMemoryResult:
    return HistoricalMemoryResult(
        canonical_digest="abc123canonical",
        seen_before=True,
        matching_cluster_ids=("cluster-x",),
        prior_member_failures=("failure-a",),
        prior_interventions=(
            PriorInterventionSummary(
                intervention_id="cand-a",
                failure_id="failure-a",
                ranking_rank=1,
                ranking_score=116,
                ranking_observed_effect="failure_removed",
            ),
        ),
        prior_observed_effects=("failure_removed",),
        provenance=(Provenance(artifact_id="failure_clustering", path="clusters.json"),),
    )


def test_fake_provider_returns_evidence_only_debug_plan() -> None:
    provider = FakeSupervisorProvider()
    evidence = build_supervisor_evidence(mvp_summary=_summary(), hkg_memory=_memory())

    plan = supervise_debug(evidence, provider)

    assert plan.status == "available"
    assert plan.provider_name == "fake-supervisor"
    assert any("Observed-effect counts" in item for item in plan.evidence_summary)
    assert any("cluster-x" in item for item in plan.recommended_next_checks)
    assert any("not causal" in item for item in plan.risks_uncertainties)
    assert provider.requests
    assert provider.requests[0].prompt == SUPERVISOR_EVIDENCE_ONLY_PROMPT
    prompt = provider.requests[0].prompt.lower()
    assert "use only the supplied structured evidence" in prompt
    assert "do not run tools" in prompt
    assert "do not claim causality" in prompt
    assert "generate patches" in prompt


def test_default_supervisor_requires_no_provider_or_api_key() -> None:
    evidence = build_supervisor_evidence(mvp_summary=_summary())

    plan = supervise_debug(evidence)

    assert plan.status == "unavailable"
    assert plan.provider_name == "none"
    assert any("No supervisor provider is configured" in item for item in plan.risks_uncertainties)
    assert any("API key" in item for item in plan.risks_uncertainties)
    assert plan.recommended_next_checks == []


def test_supervisor_input_preserves_structured_artifact_references() -> None:
    evidence = build_supervisor_evidence(mvp_summary=_summary(), hkg_memory=_memory())

    refs = {(ref.name, ref.reference) for ref in evidence.artifact_references}

    assert ("matrix", "/demo/matrix") in refs
    assert ("stage:inspect-run", "/demo/run") in refs
    assert ("outcome:cand-a", "/demo/matrix/cand-a") in refs
    assert ("comparison:cand-a", "/demo/matrix/cand-a") in refs
    assert ("ranking:cand-a", "/demo/matrix/cand-a") in refs
    assert ("memory:failure_clustering", "clusters.json") in refs


def test_supervisor_output_preserves_artifact_references_from_input_and_provider() -> None:
    class ProviderWithExtraReference(FakeSupervisorProvider):
        name = "fake-extra"

        def propose_debug_plan(self, request: SupervisorRequest) -> DebugPlanDraft:
            draft = super().propose_debug_plan(request)
            draft.cited_artifact_references.append(
                ArtifactReference(name="extra", reference="/extra/evidence.json")
            )
            return draft

    evidence = build_supervisor_evidence(mvp_summary=_summary(), hkg_memory=_memory())
    plan = supervise_debug(evidence, ProviderWithExtraReference())

    refs = {(ref.name, ref.reference) for ref in plan.cited_artifact_references}
    assert ("matrix", "/demo/matrix") in refs
    assert ("memory:failure_clustering", "clusters.json") in refs
    assert ("extra", "/extra/evidence.json") in refs


def test_supervisor_evidence_is_deterministic() -> None:
    first = build_supervisor_evidence(mvp_summary=_summary(), hkg_memory=_memory())
    second = build_supervisor_evidence(mvp_summary=_summary(), hkg_memory=_memory())
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
