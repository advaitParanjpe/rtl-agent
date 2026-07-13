"""Read-only deterministic query helpers for Hardware Knowledge Graph v0.

This module is intentionally small: it indexes an already constructed or
serialized HKG artifact and returns typed graph model objects in deterministic
order. It does not infer, mutate, execute, patch, or introduce new graph
construction semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rtl_agent.hkg.models import EdgeType, HkgEdge, HkgGraph, HkgNode, NodeType, Provenance


class HkgQueryError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExperimentOutcomeResult:
    """One experiment associated with an intervention and its observed outcomes."""

    experiment: HkgNode
    outcomes: tuple[HkgNode, ...]


class HkgQuery:
    """Deterministic read-only query API over one HKG graph artifact."""

    def __init__(self, graph: HkgGraph) -> None:
        self.graph = graph
        self._nodes = {node.node_id: node for node in graph.nodes}
        self._edges = {edge.edge_id: edge for edge in graph.edges}
        self._outgoing: dict[str, list[HkgEdge]] = {}
        self._incoming: dict[str, list[HkgEdge]] = {}
        self._nodes_by_type: dict[str, list[HkgNode]] = {}
        for node in graph.nodes:
            self._nodes_by_type.setdefault(str(node.type), []).append(node)
        for edge in graph.edges:
            self._outgoing.setdefault(edge.source, []).append(edge)
            self._incoming.setdefault(edge.target, []).append(edge)
        for edges in self._outgoing.values():
            edges.sort(key=lambda e: e.edge_id)
        for edges in self._incoming.values():
            edges.sort(key=lambda e: e.edge_id)
        for nodes in self._nodes_by_type.values():
            nodes.sort(key=lambda n: n.node_id)

    def get_node(self, node_id: str) -> HkgNode | None:
        return self._nodes.get(node_id)

    def list_nodes_by_type(self, node_type: NodeType | str) -> list[HkgNode]:
        return list(self._nodes_by_type.get(str(node_type), []))

    def outgoing_edges(
        self, node_id: str, edge_type: EdgeType | str | None = None
    ) -> list[HkgEdge]:
        return _filter_edges(self._outgoing.get(node_id, []), edge_type)

    def incoming_edges(
        self, node_id: str, edge_type: EdgeType | str | None = None
    ) -> list[HkgEdge]:
        return _filter_edges(self._incoming.get(node_id, []), edge_type)

    def find_signals(self, *, module: str | None = None, name: str | None = None) -> list[HkgNode]:
        signals: list[HkgNode]
        if module is not None:
            module_nodes = [
                node
                for node in self.list_nodes_by_type(NodeType.MODULE)
                if node.label == module or node.node_id == module
            ]
            if not module_nodes:
                return []
            by_id: dict[str, HkgNode] = {}
            for module_node in module_nodes:
                for edge in self.outgoing_edges(module_node.node_id, EdgeType.CONTAINS):
                    target = self._nodes.get(edge.target)
                    if target is not None and str(target.type) == str(NodeType.SIGNAL):
                        by_id[target.node_id] = target
            signals = list(by_id.values())
        else:
            signals = self.list_nodes_by_type(NodeType.SIGNAL)

        if name is not None:
            signals = [
                signal
                for signal in signals
                if signal.label == name
                or signal.node_id == name
                or signal.attributes.get("full_name") == name
                or (signal.attributes.get("full_name") or "").endswith(f".{name}")
            ]
        return sorted(signals, key=lambda n: n.node_id)

    def find_failures_by_canonical_fingerprint(self, canonical_digest: str) -> list[HkgNode]:
        canonical_id = f"{NodeType.CANONICAL_FINGERPRINT}:{canonical_digest}"
        if canonical_id not in self._nodes:
            return []
        failures = [
            self._nodes[edge.source]
            for edge in self.incoming_edges(canonical_id, EdgeType.REFERENCES)
            if edge.source in self._nodes
            and str(self._nodes[edge.source].type) == str(NodeType.FAILURE)
            and edge.attributes.get("role") == "fingerprint"
        ]
        return sorted(failures, key=lambda n: n.node_id)

    def find_cluster_members(self, cluster_id: str) -> list[HkgNode]:
        clusters = [
            node
            for node in self.list_nodes_by_type(NodeType.FAILURE_CLUSTER)
            if node.node_id == cluster_id or node.label == cluster_id
        ]
        if not clusters:
            return []
        node_id = clusters[0].node_id
        members = [
            self._nodes[edge.source]
            for edge in self.incoming_edges(node_id, EdgeType.BELONGS_TO_CLUSTER)
            if edge.source in self._nodes
            and str(self._nodes[edge.source].type) == str(NodeType.FAILURE)
        ]
        return sorted(members, key=lambda n: n.node_id)

    def find_interventions_for_failure(self, failure_id: str) -> list[HkgNode]:
        failures = [
            node
            for node in self.list_nodes_by_type(NodeType.FAILURE)
            if node.node_id == failure_id or node.label == failure_id
        ]
        if not failures:
            return []
        by_id: dict[str, HkgNode] = {}
        for failure in failures:
            for edge in self.outgoing_edges(failure.node_id, EdgeType.GENERATED):
                intervention = self._nodes.get(edge.target)
                if intervention is not None and str(intervention.type) == str(
                    NodeType.INTERVENTION
                ):
                    by_id[intervention.node_id] = intervention
        return [by_id[node_id] for node_id in sorted(by_id)]

    def find_experiments_for_intervention(
        self, intervention_id: str
    ) -> list[ExperimentOutcomeResult]:
        intervention_nodes = [
            node
            for node in self.list_nodes_by_type(NodeType.INTERVENTION)
            if node.node_id == intervention_id or node.label == intervention_id
        ]
        if not intervention_nodes:
            return []
        experiments_by_id: dict[str, HkgNode] = {}
        for intervention in intervention_nodes:
            for edge in self.incoming_edges(intervention.node_id, EdgeType.REFERENCES):
                experiment = self._nodes.get(edge.source)
                if (
                    experiment is not None
                    and str(experiment.type) == str(NodeType.EXPERIMENT)
                    and edge.attributes.get("role") == "tested"
                ):
                    experiments_by_id[experiment.node_id] = experiment
        experiments = list(experiments_by_id.values())
        results: list[ExperimentOutcomeResult] = []
        for experiment in sorted(experiments, key=lambda n: n.node_id):
            outcomes = tuple(
                sorted(
                    (
                        self._nodes[edge.target]
                        for edge in self.outgoing_edges(experiment.node_id, EdgeType.PRODUCED)
                        if edge.target in self._nodes
                        and str(self._nodes[edge.target].type) == str(NodeType.OBSERVED_EFFECT)
                    ),
                    key=lambda n: n.node_id,
                )
            )
            results.append(ExperimentOutcomeResult(experiment=experiment, outcomes=outcomes))
        return results

    def get_provenance(self, element_id: str) -> list[Provenance]:
        node = self._nodes.get(element_id)
        if node is not None:
            return list(node.provenance)
        edge = self._edges.get(element_id)
        if edge is not None:
            return list(edge.provenance)
        return []


def load_graph(path: Path) -> HkgGraph:
    try:
        return HkgGraph.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise HkgQueryError(f"HKG graph is unreadable: {path} ({exc})") from exc


def query_graph(graph: HkgGraph) -> HkgQuery:
    return HkgQuery(graph)


def query_graph_file(path: Path) -> HkgQuery:
    return HkgQuery(load_graph(path))


def _filter_edges(edges: list[HkgEdge], edge_type: EdgeType | str | None) -> list[HkgEdge]:
    if edge_type is None:
        return list(edges)
    wanted = str(edge_type)
    return [edge for edge in edges if str(edge.type) == wanted]
