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
    lookup_historical_failure,
    query_graph,
    query_graph_file,
    serialize_graph,
    write_graph,
)
from rtl_agent.hkg.models import EdgeType, HkgEdge, HkgGraph, HkgNode, NodeType
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
        semantic_digest=f"sd-{candidate_id}",
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
        bundle.matrix_prov = Provenance(
            source_id="mvp:test", artifact_id="experiment-matrix", schema_version=1
        )
        bundle.interventions = _interventions()
        bundle.interventions_prov = Provenance(
            source_id="mvp:test", artifact_id="intervention-templates", schema_version=1
        )
        bundle.experiment_comparisons = _comparisons()
        bundle.experiment_comparisons_prov = Provenance(
            source_id="mvp:test", artifact_id="mvp-summary", schema_version=1
        )
        bundle.intervention_rankings = _rankings()
        bundle.intervention_rankings_prov = Provenance(
            source_id="mvp:test", artifact_id="mvp-summary", schema_version=1
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
    failure = next(node for node in graph.nodes if node.type == "failure")
    assert failure.provenance and failure.provenance[0].artifact_id == "run-manifest"
    # The signal-source map provenance carries a schema version and a content hash.
    module = next(n for n in graph.nodes if n.type == "module")
    prov = module.provenance[0]
    assert prov.artifact_id == "signal-source-map"
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
    failure = next(node for node in graph.nodes if node.type == "failure")
    cand_a = next(
        node for node in graph.nodes if node.type == "intervention" and node.label == "cand-a"
    )
    cand_b_experiment = next(
        node for node in graph.nodes if node.type == "experiment" and node.label == "cand-b"
    )
    cand_a_experiment = next(
        node for node in graph.nodes if node.type == "experiment" and node.label == "cand-a"
    )
    removed = next(
        node
        for node in graph.nodes
        if node.type == "observed_effect" and node.label == "failure_removed"
    )
    edges = {(e.type, e.source, e.target) for e in graph.edges}
    assert ("generated", failure.node_id, cand_a.node_id) in edges
    assert ("produced", cand_a_experiment.node_id, removed.node_id) in edges
    assert ("references", cand_a_experiment.node_id, cand_a.node_id) in edges
    # The changed experiment references its result canonical fingerprint.
    assert ("references", cand_b_experiment.node_id, "canonical_fingerprint:rc-b") in edges
    ranking = next(
        edge
        for edge in graph.edges
        if edge.source == cand_a.node_id and edge.attributes.get("role") == "ranking"
    )
    assert ranking.attributes["ranking_rank"] == "1"
    assert cand_b_experiment.attributes["canonical_changed"] == "True"


def test_belongs_to_cluster_edges(tmp_path: Path) -> None:
    graph = build_hkg(
        [_bundle(tmp_path, with_counterfactual=False)],
        graph_id="g",
        cluster_report=_cluster("failure-core", "canon-x"),
    )
    failure = next(node for node in graph.nodes if node.type == "failure")
    edges = {(e.type, e.source, e.target) for e in graph.edges}
    assert ("belongs_to_cluster", failure.node_id, "failure_cluster:cluster-abc") in edges


def test_missing_canonical_fingerprint_warns(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path, with_counterfactual=False)
    bundle.fingerprint = bundle.fingerprint.model_copy(update={"canonical_digest": ""})
    graph = build_hkg([bundle], graph_id="g")
    assert any("no canonical fingerprint" in w for w in graph.warnings)
    assert "canonical_fingerprint" not in graph.node_type_counts


def test_query_get_node_and_list_nodes_by_type(tmp_path: Path) -> None:
    graph = build_hkg([_bundle(tmp_path)], graph_id="g")
    query = query_graph(graph)

    failure_id = next(node.node_id for node in graph.nodes if node.type == "failure")
    failure = query.get_node(failure_id)
    assert failure is not None
    assert failure.type == "failure"
    assert query.get_node("failure:missing") is None

    signals = query.list_nodes_by_type(NodeType.SIGNAL)
    assert signals
    assert [node.node_id for node in signals] == sorted(node.node_id for node in signals)
    assert query.list_nodes_by_type("not_a_node_type") == []


def test_query_incoming_and_outgoing_edges(tmp_path: Path) -> None:
    graph = build_hkg([_bundle(tmp_path)], graph_id="g")
    query = query_graph(graph)

    failure_id = next(node.node_id for node in graph.nodes if node.type == "failure")
    intervention_id = next(
        node.node_id
        for node in graph.nodes
        if node.type == "intervention" and node.label == "cand-a"
    )
    outgoing = query.outgoing_edges(failure_id)
    assert outgoing
    assert [edge.edge_id for edge in outgoing] == sorted(edge.edge_id for edge in outgoing)
    assert query.outgoing_edges(failure_id, EdgeType.GENERATED)
    assert query.incoming_edges(intervention_id, EdgeType.REFERENCES)
    assert query.outgoing_edges("missing") == []
    assert query.incoming_edges("missing") == []


def test_query_find_signals_by_module_and_name(tmp_path: Path) -> None:
    graph = build_hkg([_bundle(tmp_path)], graph_id="g")
    query = query_graph(graph)

    module_signals = query.find_signals(module="core")
    assert "hold" in {node.label for node in module_signals}
    assert query.find_signals(module="core", name="hold")[0].label == "hold"
    assert query.find_signals(name="core.hold")[0].label == "hold"
    assert query.find_signals(module="missing") == []
    assert query.find_signals(module="core", name="missing") == []


def test_query_find_failures_by_canonical_fingerprint(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path, with_counterfactual=False)
    graph = build_hkg([bundle], graph_id="g")
    query = query_graph(graph)

    failures = query.find_failures_by_canonical_fingerprint(bundle.fingerprint.canonical_digest)
    assert [node.label for node in failures] == ["failure-core"]
    assert query.find_failures_by_canonical_fingerprint("missing") == []


def test_query_find_cluster_members(tmp_path: Path) -> None:
    graph = build_hkg(
        [_bundle(tmp_path, with_counterfactual=False)],
        graph_id="g",
        cluster_report=_cluster("failure-core", "canon-x"),
    )
    query = query_graph(graph)

    assert [node.label for node in query.find_cluster_members("cluster-abc")] == ["failure-core"]
    assert [node.label for node in query.find_cluster_members("failure_cluster:cluster-abc")] == [
        "failure-core"
    ]
    assert query.find_cluster_members("missing") == []


def test_query_interventions_and_experiment_outcomes(tmp_path: Path) -> None:
    graph = build_hkg([_bundle(tmp_path)], graph_id="g")
    query = query_graph(graph)

    interventions = query.find_interventions_for_failure("failure-core")
    assert [node.label for node in interventions] == ["cand-a", "cand-b"]
    assert query.find_interventions_for_failure("missing") == []

    results = query.find_experiments_for_intervention("cand-a")
    assert len(results) == 1
    assert results[0].experiment.label == "cand-a"
    assert [node.label for node in results[0].outcomes] == ["failure_removed"]
    assert query.find_experiments_for_intervention("missing") == []


def test_query_get_provenance_for_node_and_edge(tmp_path: Path) -> None:
    graph = build_hkg([_bundle(tmp_path)], graph_id="g")
    query = query_graph(graph)

    failure_id = next(node.node_id for node in graph.nodes if node.type == "failure")
    node_prov = query.get_provenance(failure_id)
    assert node_prov and node_prov[0].artifact_id == "run-manifest"
    edge = query.outgoing_edges(failure_id, EdgeType.GENERATED)[0]
    edge_prov = query.get_provenance(edge.edge_id)
    assert edge_prov and edge_prov[0].artifact_id == "intervention-templates"
    assert query.get_provenance("missing") == []


def test_query_graph_file_loads_serialized_graph(tmp_path: Path) -> None:
    graph = build_hkg([_bundle(tmp_path / "run")], graph_id="g")
    output = tmp_path / "hkg.json"
    write_graph(graph, output)

    query = query_graph_file(output)
    assert [node.label for node in query.list_nodes_by_type(NodeType.FAILURE)] == ["failure-core"]


def test_historical_memory_seen_before_match(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path, with_counterfactual=False)
    graph = build_hkg(
        [bundle],
        graph_id="g",
        cluster_report=_cluster("failure-core", bundle.fingerprint.canonical_digest),
    )

    result = lookup_historical_failure(graph, bundle.fingerprint)

    assert result.seen_before is True
    assert result.canonical_digest == bundle.fingerprint.canonical_digest
    assert result.matching_cluster_ids == ("cluster-abc",)
    assert result.prior_member_failures == ("failure-core",)
    assert result.provenance
    assert "root-cause" in result.disclaimer


def test_historical_memory_no_prior_match(tmp_path: Path) -> None:
    graph = build_hkg([_bundle(tmp_path, with_counterfactual=False)], graph_id="g")

    result = lookup_historical_failure(graph, "missing-canonical")

    assert result.seen_before is False
    assert result.canonical_digest == "missing-canonical"
    assert result.matching_cluster_ids == ()
    assert result.prior_member_failures == ()
    assert result.prior_interventions == ()
    assert result.prior_observed_effects == ()
    assert result.provenance == ()


def test_historical_memory_multiple_prior_members() -> None:
    graph = _manual_history_graph()

    result = lookup_historical_failure(graph, "canon-shared")

    assert result.seen_before is True
    assert result.matching_cluster_ids == ("cluster-shared",)
    assert result.prior_member_failures == ("failure-a", "failure-b")
    assert result.prior_interventions == ()
    assert result.prior_observed_effects == ()


def test_historical_memory_prior_interventions_outcomes_and_rankings(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    graph = build_hkg(
        [bundle],
        graph_id="g",
        cluster_report=_cluster("failure-core", bundle.fingerprint.canonical_digest),
    )

    result = lookup_historical_failure(query_graph(graph), bundle.fingerprint.canonical_digest)

    assert result.seen_before is True
    assert [item.intervention_id for item in result.prior_interventions] == ["cand-a", "cand-b"]
    cand_a = result.prior_interventions[0]
    assert cand_a.failure_id == "failure-core"
    assert cand_a.template_kind == "hold_register"
    assert cand_a.confidence == "high_evidence"
    assert cand_a.ranking_rank == 1
    assert cand_a.ranking_score == 116
    assert cand_a.ranking_ranked is True
    assert cand_a.ranking_observed_effect == "failure_removed"
    assert cand_a.provenance
    assert result.prior_observed_effects == ("failure_changed", "failure_removed")
    assert [(item.intervention_id, item.observed_effects) for item in result.prior_experiments] == [
        ("cand-a", ("failure_removed",)),
        ("cand-b", ("failure_changed",)),
    ]
    assert result.provenance


def _manual_history_graph() -> HkgGraph:
    prov = Provenance(artifact_id="manual_test", schema_version=1, content_sha256="abc")
    nodes = [
        HkgNode(
            node_id="canonical_fingerprint:canon-shared",
            type=NodeType.CANONICAL_FINGERPRINT,
            label="canon-shared",
            attributes={"canonical_digest": "canon-shared"},
            provenance=[prov],
        ),
        HkgNode(
            node_id="failure:failure-a",
            type=NodeType.FAILURE,
            label="failure-a",
            provenance=[prov],
        ),
        HkgNode(
            node_id="failure:failure-b",
            type=NodeType.FAILURE,
            label="failure-b",
            provenance=[prov],
        ),
        HkgNode(
            node_id="failure_cluster:cluster-shared",
            type=NodeType.FAILURE_CLUSTER,
            label="cluster-shared",
            attributes={"canonical_digest": "canon-shared", "size": "2"},
            provenance=[prov],
        ),
    ]
    edges = [
        HkgEdge(
            edge_id="references|failure:failure-a|canonical_fingerprint:canon-shared",
            type=EdgeType.REFERENCES,
            source="failure:failure-a",
            target="canonical_fingerprint:canon-shared",
            attributes={"role": "fingerprint"},
            provenance=[prov],
        ),
        HkgEdge(
            edge_id="references|failure:failure-b|canonical_fingerprint:canon-shared",
            type=EdgeType.REFERENCES,
            source="failure:failure-b",
            target="canonical_fingerprint:canon-shared",
            attributes={"role": "fingerprint"},
            provenance=[prov],
        ),
        HkgEdge(
            edge_id="belongs_to_cluster|failure:failure-a|failure_cluster:cluster-shared",
            type=EdgeType.BELONGS_TO_CLUSTER,
            source="failure:failure-a",
            target="failure_cluster:cluster-shared",
            provenance=[prov],
        ),
        HkgEdge(
            edge_id="belongs_to_cluster|failure:failure-b|failure_cluster:cluster-shared",
            type=EdgeType.BELONGS_TO_CLUSTER,
            source="failure:failure-b",
            target="failure_cluster:cluster-shared",
            provenance=[prov],
        ),
    ]
    return HkgGraph(
        graph_id="manual-history",
        node_count=len(nodes),
        edge_count=len(edges),
        node_type_counts={"canonical_fingerprint": 1, "failure": 2, "failure_cluster": 1},
        edge_type_counts={"belongs_to_cluster": 2, "references": 2},
        nodes=nodes,
        edges=edges,
    )
