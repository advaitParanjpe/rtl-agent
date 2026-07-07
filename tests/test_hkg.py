from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from rtl_agent.artifacts import RunStore
from rtl_agent.experiment_comparison_models import (
    ExperimentComparison,
    FingerprintRelationship,
    SignalChange,
)
from rtl_agent.experiment_matrix_models import ExperimentMatrixReport, MatrixRow, MatrixSummary
from rtl_agent.failure_clustering_models import FailureCluster, FailureClusterReport
from rtl_agent.failure_intelligence_run import run_failure_intelligence
from rtl_agent.hkg import (
    FailureBundle,
    Provenance,
    build_hkg,
    load_failure_bundle,
    serialize_graph,
    write_graph,
)
from rtl_agent.intervention_ranking_models import InterventionRanking, RankingFactor
from rtl_agent.intervention_template_models import (
    ConfidenceLevel,
    EvidenceAnchor,
    InterventionCandidate,
    InterventionTemplateReport,
    TemplateKind,
    TemplateSummary,
)

# --------------------------------------------------------------------------- #
# Hermetic failure-intelligence run (no simulator).
# --------------------------------------------------------------------------- #

CORE_SV = """module core (
    input  logic       clk,
    input  logic [7:0] din,
    output logic [7:0] hold,
    output logic [7:0] dout
);
    assign hold = din;
    assign dout = hold;
endmodule
"""

_VCD_HEADER = (
    "$timescale 1ns $end\n"
    "$scope module tb $end\n$scope module core $end\n"
    "$var reg 8 ! dout [7:0] $end\n"
    '$var reg 8 " hold [7:0] $end\n'
    "$var reg 8 # din [7:0] $end\n"
    "$upscope $end\n$upscope $end\n$enddefinitions $end\n"
    '$dumpvars\nb00000000 !\nb00000000 "\nb00000000 #\n$end\n'
)


def _write_vcds(root: Path) -> tuple[Path, Path]:
    failing = root / "failing.vcd"
    passing = root / "passing.vcd"
    load = '#30\nb10101010 !\nb10101010 "\nb10101010 #\n'
    failing.write_text(
        _VCD_HEADER + load + '#40\nbxxxxxxxx !\nbxxxxxxxx "\n#50\n', encoding="utf-8"
    )
    passing.write_text(_VCD_HEADER + load + "#50\n", encoding="utf-8")
    return failing, passing


def _build_run(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    rtl = tmp_path / "rtl"
    rtl.mkdir()
    (rtl / "core.sv").write_text(CORE_SV, encoding="utf-8")
    failing, passing = _write_vcds(tmp_path)
    store = RunStore(tmp_path / "runs", run_id="failure-core")
    store.create()
    run_failure_intelligence(
        store,
        failing_vcd=failing,
        passing_vcd=passing,
        repository_root=rtl,
        failure_time=40,
        before=15,
        after=15,
    )
    return store.run_dir


# --------------------------------------------------------------------------- #
# Synthetic counterfactual + cluster artifacts.
# --------------------------------------------------------------------------- #


def _matrix() -> ExperimentMatrixReport:
    summary = MatrixSummary(
        total_requested=2,
        executed=2,
        skipped=0,
        cache_hits=0,
        failures_removed=1,
        same_family=0,
        changed_family=1,
        no_effect=0,
        infrastructure_failures=0,
        insufficient_evidence=0,
    )
    rows = [
        MatrixRow(
            intervention_id="cand-a",
            intervention_digest="d1",
            experiment_digest="e1",
            execution_status="executed",
            baseline_exact_digest="be",
            baseline_family_digest="bf",
            observed_effect="failure_removed",
            result_failure_signals=[],
        ),
        MatrixRow(
            intervention_id="cand-b",
            intervention_digest="d2",
            experiment_digest="e2",
            execution_status="executed",
            baseline_exact_digest="be",
            baseline_family_digest="bf",
            observed_effect="failure_changed",
            result_family_digest="rf",
            result_canonical_digest="rc-b",
            result_failure_signals=["hold"],
        ),
    ]
    return ExperimentMatrixReport(
        matrix_id="m1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        baseline_run="/run",
        baseline_exact_digest="be",
        baseline_family_digest="bf",
        target_repo="/repo",
        command_name="sim",
        minimized_stimulus="/min.json",
        minimized_stimulus_digest="ms",
        reduction_report="/red.json",
        max_experiments=12,
        summary=summary,
        rows=rows,
    )


def _candidate(candidate_id: str, signal: str) -> InterventionCandidate:
    return InterventionCandidate(
        candidate_id=candidate_id,
        template_kind=TemplateKind.HOLD_REGISTER,
        hypothesis="?",
        confidence=ConfidenceLevel.HIGH_EVIDENCE,
        file="rtl/core.sv",
        source_file="core.sv",
        source_line=6,
        source_span_text="hold <= din;",
        source_sha256="s",
        file_sha256="f",
        replace_old="hold <= din;",
        proposed_replacement="hold <= hold;",
        affected_signal=signal,
        evidence=EvidenceAnchor(signal=f"core.{signal}", leaf=signal, mapping_status="exact"),
        semantic_digest="sd",
        experiment_note="experiment proposal only",
    )


def _interventions() -> InterventionTemplateReport:
    return InterventionTemplateReport(
        generation_id="g1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        failure_run="/run",
        target_repo="/repo",
        max_candidates=8,
        summary=TemplateSummary(
            templates_considered=2,
            candidates_emitted=2,
            sites_skipped=0,
            high_evidence=2,
            moderate_evidence=0,
            low_evidence=0,
        ),
        candidates=[_candidate("cand-a", "hold"), _candidate("cand-b", "dout")],
    )


def _cluster(failure_id: str, canonical: str) -> FailureClusterReport:
    cluster = FailureCluster(
        cluster_id="cluster-abc",
        canonical_digest=canonical,
        size=1,
        representative_id=failure_id,
        representative_reason="only member",
        members=[failure_id],
        family_digests=["fam"],
    )
    return FailureClusterReport(
        total_failures=1,
        cluster_count=1,
        canonical_cluster_count=1,
        insufficient_count=0,
        clusters=[cluster],
        assignments={failure_id: "cluster-abc"},
    )


def _comparisons() -> list[ExperimentComparison]:
    return [
        ExperimentComparison(
            intervention_id="cand-a",
            template_kind="hold_register",
            confidence="high_evidence",
            execution_status="executed",
            comparable=True,
            observed_effect="failure_removed",
            fingerprint=FingerprintRelationship(relation="removed"),
            baseline_canonical_digest="bc",
            summary="failure removed in the bounded experiment",
        ),
        ExperimentComparison(
            intervention_id="cand-b",
            template_kind="hold_register",
            confidence="high_evidence",
            execution_status="executed",
            comparable=True,
            observed_effect="failure_changed",
            fingerprint=FingerprintRelationship(relation="canonical_changed"),
            baseline_canonical_digest="bc",
            result_canonical_digest="rc-b",
            canonical_changed=True,
            signal_change=SignalChange(baseline_signals=["dout"], result_signals=["hold"]),
            summary="failure changed in the bounded experiment",
        ),
    ]


def _rankings() -> list[InterventionRanking]:
    return [
        InterventionRanking(
            intervention_id="cand-a",
            template_kind="hold_register",
            confidence="high_evidence",
            rank=1,
            score=116,
            ranked=True,
            observed_effect="failure_removed",
            result_cluster_id="cluster-abc",
            result_cluster_size=1,
            factors=[RankingFactor(factor="observed_effect:failure_removed", points=100)],
            explanation="Ranked from existing experiment evidence.",
            evidence_refs=["experiment:cand-a"],
        ),
        InterventionRanking(
            intervention_id="cand-b",
            template_kind="hold_register",
            confidence="high_evidence",
            rank=2,
            score=89,
            ranked=True,
            observed_effect="failure_changed",
            result_cluster_id="cluster-abc",
            result_cluster_size=1,
            factors=[RankingFactor(factor="observed_effect:failure_changed", points=60)],
            explanation="Ranked from existing experiment evidence.",
            evidence_refs=["experiment:cand-b"],
        ),
    ]


def _bundle(tmp_path: Path, *, with_counterfactual: bool = True) -> FailureBundle:
    run_dir = _build_run(tmp_path)
    bundle = load_failure_bundle("failure-core", run_dir)
    if with_counterfactual:
        bundle.matrix = _matrix()
        bundle.matrix_prov = Provenance(artifact_id="experiment_matrix", schema_version=1)
        bundle.interventions = _interventions()
        bundle.interventions_prov = Provenance(
            artifact_id="intervention_templates", schema_version=1
        )
        bundle.experiment_comparisons = _comparisons()
        bundle.experiment_comparisons_prov = Provenance(
            artifact_id="experiment_comparisons", schema_version=1
        )
        bundle.intervention_rankings = _rankings()
        bundle.intervention_rankings_prov = Provenance(
            artifact_id="intervention_rankings", schema_version=1
        )
    return bundle


# --------------------------------------------------------------------------- #
# Tests.
# --------------------------------------------------------------------------- #


def test_structural_graph_from_run(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path, with_counterfactual=False)
    graph = build_hkg([bundle], graph_id="g")
    types = graph.node_type_counts
    for node_type in ("failure", "canonical_fingerprint", "module", "signal", "source_location"):
        assert types.get(node_type, 0) >= 1, (node_type, types)
    edges = graph.edge_type_counts
    assert edges.get("contains", 0) >= 1
    assert edges.get("originated_from", 0) >= 1
    assert edges.get("references", 0) >= 1
    # dout depends on hold depends on din -> dependency edges exist.
    assert edges.get("depends_on", 0) >= 1
    assert graph.node_count == len(graph.nodes)
    assert graph.edge_count == len(graph.edges)


def test_all_node_and_edge_types_present(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    graph = build_hkg([bundle], graph_id="g", cluster_report=_cluster("failure-core", "canon"))
    node_types = set(graph.node_type_counts)
    edge_types = set(graph.edge_type_counts)
    assert node_types == {
        "module",
        "signal",
        "source_location",
        "failure",
        "canonical_fingerprint",
        "failure_cluster",
        "intervention",
        "experiment",
        "observed_effect",
    }
    assert edge_types == {
        "contains",
        "drives",
        "depends_on",
        "originated_from",
        "belongs_to_cluster",
        "generated",
        "produced",
        "references",
    }


def test_provenance_is_retained(tmp_path: Path) -> None:
    graph = build_hkg([_bundle(tmp_path)], graph_id="g")
    by_id = {n.node_id: n for n in graph.nodes}
    failure = by_id["failure:failure-core"]
    assert failure.provenance and failure.provenance[0].artifact_id == "run_manifest"
    # The signal-source map provenance carries a schema version and a content hash.
    module = next(n for n in graph.nodes if n.type == "module")
    prov = module.provenance[0]
    assert prov.artifact_id == "signal_source_map_report"
    assert prov.schema_version is not None
    assert prov.content_sha256 and prov.path
    # Every node and edge has at least one provenance record.
    assert all(n.provenance for n in graph.nodes)
    assert all(e.provenance for e in graph.edges)


def test_repeated_ingestion_is_byte_identical(tmp_path: Path) -> None:
    bundle_a = _bundle(tmp_path / "a")
    graph_a = build_hkg([bundle_a], graph_id="g", cluster_report=_cluster("failure-core", "c"))
    graph_b = build_hkg([bundle_a], graph_id="g", cluster_report=_cluster("failure-core", "c"))
    assert serialize_graph(graph_a) == serialize_graph(graph_b)
    # Nodes and edges are sorted by id.
    assert [n.node_id for n in graph_a.nodes] == sorted(n.node_id for n in graph_a.nodes)
    assert [e.edge_id for e in graph_a.edges] == sorted(e.edge_id for e in graph_a.edges)
    output = tmp_path / "hkg.json"
    write_graph(graph_a, output)
    assert output.read_text(encoding="utf-8") == serialize_graph(graph_a)


def test_counterfactual_edges(tmp_path: Path) -> None:
    graph = build_hkg([_bundle(tmp_path)], graph_id="g")
    edges = {(e.type, e.source, e.target) for e in graph.edges}
    assert ("generated", "failure:failure-core", "intervention:cand-a") in edges
    assert ("produced", "experiment:cand-a", "observed_effect:failure_removed") in edges
    assert ("references", "experiment:cand-a", "intervention:cand-a") in edges
    # The changed experiment references its result canonical fingerprint.
    assert ("references", "experiment:cand-b", "canonical_fingerprint:rc-b") in edges
    interventions = {n.node_id: n for n in graph.nodes if n.type == "intervention"}
    assert interventions["intervention:cand-a"].attributes["ranking_rank"] == "1"
    experiments = {n.node_id: n for n in graph.nodes if n.type == "experiment"}
    assert experiments["experiment:cand-b"].attributes["canonical_changed"] == "True"


def test_belongs_to_cluster_edges(tmp_path: Path) -> None:
    graph = build_hkg(
        [_bundle(tmp_path, with_counterfactual=False)],
        graph_id="g",
        cluster_report=_cluster("failure-core", "canon-x"),
    )
    edges = {(e.type, e.source, e.target) for e in graph.edges}
    assert ("belongs_to_cluster", "failure:failure-core", "failure_cluster:cluster-abc") in edges


def test_missing_canonical_fingerprint_warns(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path, with_counterfactual=False)
    bundle.fingerprint = bundle.fingerprint.model_copy(update={"canonical_digest": ""})
    graph = build_hkg([bundle], graph_id="g")
    assert any("no canonical fingerprint" in w for w in graph.warnings)
    assert "canonical_fingerprint" not in graph.node_type_counts
