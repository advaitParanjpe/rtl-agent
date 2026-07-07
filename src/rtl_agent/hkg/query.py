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
            module_node = self.get_node(f"{NodeType.MODULE}:{module}")
            if module_node is None:
                return []
            signals = [
                self._nodes[edge.target]
                for edge in self.outgoing_edges(module_node.node_id, EdgeType.CONTAINS)
                if edge.target in self._nodes
                and str(self._nodes[edge.target].type) == str(NodeType.SIGNAL)
            ]
        else:
            signals = self.list_nodes_by_type(NodeType.SIGNAL)

        if name is not None:
            signals = [
                signal
                for signal in signals
                if signal.label == name
                or signal.node_id == f"{NodeType.SIGNAL}:{name}"
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
        node_id = _node_id(NodeType.FAILURE_CLUSTER, cluster_id)
        if node_id not in self._nodes:
            return []
        members = [
            self._nodes[edge.source]
            for edge in self.incoming_edges(node_id, EdgeType.BELONGS_TO_CLUSTER)
            if edge.source in self._nodes
            and str(self._nodes[edge.source].type) == str(NodeType.FAILURE)
        ]
        return sorted(members, key=lambda n: n.node_id)

    def find_interventions_for_failure(self, failure_id: str) -> list[HkgNode]:
        node_id = _node_id(NodeType.FAILURE, failure_id)
        if node_id not in self._nodes:
            return []
        interventions = [
            self._nodes[edge.target]
            for edge in self.outgoing_edges(node_id, EdgeType.GENERATED)
            if edge.target in self._nodes
            and str(self._nodes[edge.target].type) == str(NodeType.INTERVENTION)
        ]
        return sorted(interventions, key=lambda n: n.node_id)

    def find_experiments_for_intervention(
        self, intervention_id: str
    ) -> list[ExperimentOutcomeResult]:
        node_id = _node_id(NodeType.INTERVENTION, intervention_id)
        if node_id not in self._nodes:
            return []
        experiments = [
            self._nodes[edge.source]
            for edge in self.incoming_edges(node_id, EdgeType.REFERENCES)
            if edge.source in self._nodes
            and str(self._nodes[edge.source].type) == str(NodeType.EXPERIMENT)
            and edge.attributes.get("role") == "tested"
        ]
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


def _node_id(node_type: NodeType, key_or_id: str) -> str:
    prefix = f"{node_type}:"
    if key_or_id.startswith(prefix):
        return key_or_id
    return f"{prefix}{key_or_id}"
