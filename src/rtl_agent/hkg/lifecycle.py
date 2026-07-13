"""Explicit deterministic persistence lifecycle for the local HKG store."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable
from hashlib import sha256
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from rtl_agent.hkg.builder import FailureBundle, HkgBuildError, build_hkg, serialize_graph
from rtl_agent.hkg.identity import edge_id, semantic_node_id
from rtl_agent.hkg.lifecycle_models import (
    DEFAULT_HKG_ROOT,
    HKG_GRAPH_FILENAME,
    HKG_MANIFEST_FILENAME,
    HKG_STORE_MANIFEST_SCHEMA_VERSION,
    HkgInspection,
    HkgOperation,
    HkgOperationSummary,
    HkgStoreManifest,
)
from rtl_agent.hkg.models import (
    HKG_SCHEMA_VERSION,
    EdgeType,
    HkgEdge,
    HkgGraph,
    HkgNode,
    HkgSourceArtifact,
    HkgSourceRecord,
    NodeType,
    Provenance,
)
from rtl_agent.hkg.source_adapters import (
    HkgSourceError,
    HkgSourcePayload,
    load_failure_package_source,
    load_failure_run_source,
    load_mvp_demo_sources,
    source_content_sha256,
)

PERSISTENT_GRAPH_ID = "persistent-hkg-v1"


class HkgLifecycleError(RuntimeError):
    pass


class HkgConflictError(HkgLifecycleError):
    pass


def build_hkg_store(
    *,
    failure_runs: Iterable[Path] = (),
    failure_packages: Iterable[Path] = (),
    mvp_demos: Iterable[Path] = (),
    output: Path = DEFAULT_HKG_ROOT,
    overwrite: bool = False,
) -> HkgOperationSummary:
    root = _store_root(output)
    if root.exists() and any(root.iterdir()) and not overwrite:
        raise HkgLifecycleError(f"HKG store already exists; use overwrite to rebuild: {root}")
    payloads = _load_inputs(failure_runs, failure_packages, mvp_demos)
    records, bundles = _normalize_payloads(payloads)
    graph = build_hkg(
        bundles,
        graph_id=PERSISTENT_GRAPH_ID,
        sources=records,
    )
    graph = _recompute_canonical_clusters(graph)
    validate_graph(graph)
    graph_sha = _persist(root, graph)
    return _summary(
        HkgOperation.BUILD,
        graph,
        root,
        graph_sha,
        changed=True,
        added=[record.source_id for record in records],
        existing=[],
    )


def update_hkg_store(
    *,
    store: Path = DEFAULT_HKG_ROOT,
    failure_runs: Iterable[Path] = (),
    failure_packages: Iterable[Path] = (),
    mvp_demos: Iterable[Path] = (),
) -> HkgOperationSummary:
    root = _store_root(store)
    existing_graph, existing_manifest = load_hkg_store(root)
    payloads = _load_inputs(failure_runs, failure_packages, mvp_demos)
    records, bundles = _normalize_payloads(payloads)

    existing_by_id = {record.source_id: record for record in existing_graph.sources}
    added: list[str] = []
    already_present: list[str] = []
    for record in records:
        prior = existing_by_id.get(record.source_id)
        if prior is None:
            added.append(record.source_id)
        elif prior.content_sha256 != record.content_sha256 or prior != record:
            raise HkgConflictError(
                f"source identity/content conflict: {record.source_id} "
                f"({prior.content_sha256} != {record.content_sha256})"
            )
        else:
            already_present.append(record.source_id)

    if not added:
        return _summary(
            HkgOperation.UPDATE,
            existing_graph,
            root,
            existing_manifest.graph_sha256,
            changed=False,
            added=[],
            existing=already_present,
        )

    incoming = build_hkg(
        bundles,
        graph_id=PERSISTENT_GRAPH_ID,
        sources=records,
    )
    merged = merge_graphs(existing_graph, incoming)
    validate_graph(merged)
    graph_sha = _persist(root, merged)
    return _summary(
        HkgOperation.UPDATE,
        merged,
        root,
        graph_sha,
        changed=True,
        added=added,
        existing=already_present,
    )


def load_hkg_store(store: Path = DEFAULT_HKG_ROOT) -> tuple[HkgGraph, HkgStoreManifest]:
    root = _store_root(store)
    graph_path = root / HKG_GRAPH_FILENAME
    manifest_path = root / HKG_MANIFEST_FILENAME
    if not manifest_path.is_file():
        if graph_path.is_file() and _raw_schema_version(graph_path) == 1:
            raise HkgLifecycleError("legacy HKG schema 1 is read-only; rebuild it with hkg-build")
        raise HkgLifecycleError(f"HKG manifest is missing: {manifest_path}")
    if not graph_path.is_file():
        raise HkgLifecycleError(f"HKG graph is missing: {graph_path}")
    try:
        manifest_text = manifest_path.read_text(encoding="utf-8")
        manifest = HkgStoreManifest.model_validate_json(manifest_text)
    except (OSError, ValidationError, ValueError) as exc:
        raise HkgLifecycleError(f"HKG manifest is invalid: {manifest_path} ({exc})") from exc
    if manifest.schema_version != HKG_STORE_MANIFEST_SCHEMA_VERSION:
        raise HkgLifecycleError(
            f"unsupported HKG manifest schema {manifest.schema_version}; rebuild required"
        )
    if manifest.graph_file != HKG_GRAPH_FILENAME or not _safe_relative(manifest.graph_file):
        raise HkgLifecycleError(f"unsafe or unsupported HKG graph path: {manifest.graph_file}")
    if manifest_text != serialize_manifest(manifest):
        raise HkgLifecycleError("HKG manifest is not canonically serialized")

    graph_bytes = graph_path.read_bytes()
    actual_sha = sha256(graph_bytes).hexdigest()
    if actual_sha != manifest.graph_sha256:
        raise HkgLifecycleError(
            f"HKG graph hash mismatch (expected {manifest.graph_sha256}, actual {actual_sha})"
        )
    try:
        graph_text = graph_bytes.decode("utf-8")
        graph = HkgGraph.model_validate_json(graph_text)
    except (UnicodeDecodeError, ValidationError, ValueError) as exc:
        raise HkgLifecycleError(f"HKG graph is invalid JSON: {graph_path} ({exc})") from exc
    if graph.schema_version == 1:
        raise HkgLifecycleError("legacy HKG schema 1 is read-only; rebuild it with hkg-build")
    if graph.schema_version != HKG_SCHEMA_VERSION:
        raise HkgLifecycleError(
            f"unsupported HKG graph schema {graph.schema_version}; rebuild required"
        )
    if graph_text != serialize_graph(graph):
        raise HkgLifecycleError("HKG graph is not canonically serialized")
    validate_graph(graph)
    if (
        manifest.graph_schema_version != graph.schema_version
        or manifest.graph_id != graph.graph_id
        or manifest.node_count != graph.node_count
        or manifest.edge_count != graph.edge_count
        or manifest.source_count != len(graph.sources)
        or manifest.sources != graph.sources
    ):
        raise HkgLifecycleError("HKG manifest metadata does not agree with the graph")
    return graph, manifest


def inspect_hkg_store(store: Path = DEFAULT_HKG_ROOT) -> HkgInspection:
    root = _store_root(store)
    graph_path = root / HKG_GRAPH_FILENAME
    manifest_path = root / HKG_MANIFEST_FILENAME
    try:
        graph, manifest = load_hkg_store(root)
    except HkgLifecycleError as exc:
        return HkgInspection(
            valid=False,
            status="invalid",
            graph_root=root,
            graph_path=graph_path,
            manifest_path=manifest_path,
            warnings=[str(exc)],
        )
    counts = _semantic_counts(graph)
    source_types: dict[str, int] = {}
    for source in graph.sources:
        source_types[str(source.source_type)] = source_types.get(str(source.source_type), 0) + 1
    return HkgInspection(
        valid=True,
        status="valid",
        graph_root=root,
        graph_path=graph_path,
        manifest_path=manifest_path,
        graph_schema_version=graph.schema_version,
        graph_sha256=manifest.graph_sha256,
        manifest_valid=True,
        source_count=len(graph.sources),
        source_types=dict(sorted(source_types.items())),
        node_count=graph.node_count,
        edge_count=graph.edge_count,
        canonical_failure_count=counts["canonical_fingerprint"],
        intervention_count=counts["intervention"],
        experiment_count=counts["experiment"],
        observed_effect_count=counts["observed_effect"],
    )


def validate_graph(graph: HkgGraph) -> None:
    if graph.schema_version != HKG_SCHEMA_VERSION:
        raise HkgLifecycleError(f"unsupported HKG graph schema: {graph.schema_version}")
    if graph.graph_id != PERSISTENT_GRAPH_ID:
        raise HkgLifecycleError(f"unsupported persistent graph id: {graph.graph_id}")
    if graph.sources != sorted(graph.sources, key=lambda source: source.source_id):
        raise HkgLifecycleError("HKG sources are not deterministically ordered")
    source_by_id: dict[str, HkgSourceRecord] = {}
    artifacts: dict[tuple[str, str], HkgSourceArtifact] = {}
    for source in graph.sources:
        if source.source_id in source_by_id:
            raise HkgLifecycleError(f"duplicate HKG source id: {source.source_id}")
        source_by_id[source.source_id] = source
        source_artifacts = list(source.artifacts)
        if source_artifacts != sorted(
            source_artifacts, key=lambda item: (item.artifact_id, item.relative_path)
        ):
            raise HkgLifecycleError(f"source artifacts are not ordered: {source.source_id}")
        try:
            indexed_digest = source_content_sha256(source_artifacts)
        except HkgSourceError as exc:
            raise HkgLifecycleError(
                f"source artifact index is invalid: {source.source_id} ({exc})"
            ) from exc
        if source.content_sha256 != indexed_digest:
            raise HkgLifecycleError(f"source content digest is invalid: {source.source_id}")
        for artifact in source_artifacts:
            if not _safe_relative(artifact.relative_path):
                raise HkgLifecycleError(
                    f"unsafe source artifact path: {source.source_id}:{artifact.relative_path}"
                )
            key = (source.source_id, artifact.artifact_id)
            if key in artifacts:
                raise HkgLifecycleError(
                    f"duplicate source artifact id: {source.source_id}:{artifact.artifact_id}"
                )
            artifacts[key] = artifact

    node_ids = [node.node_id for node in graph.nodes]
    edge_ids = [edge.edge_id for edge in graph.edges]
    if node_ids != sorted(node_ids) or len(node_ids) != len(set(node_ids)):
        raise HkgLifecycleError("HKG node IDs are unordered or duplicated")
    if edge_ids != sorted(edge_ids) or len(edge_ids) != len(set(edge_ids)):
        raise HkgLifecycleError("HKG edge IDs are unordered or duplicated")
    if graph.node_count != len(graph.nodes) or graph.edge_count != len(graph.edges):
        raise HkgLifecycleError("HKG declared counts do not match graph contents")
    if graph.node_type_counts != _counts(str(node.type) for node in graph.nodes):
        raise HkgLifecycleError("HKG node type counts are invalid")
    if graph.edge_type_counts != _counts(str(edge.type) for edge in graph.edges):
        raise HkgLifecycleError("HKG edge type counts are invalid")
    node_set = set(node_ids)
    for edge in graph.edges:
        if edge.source not in node_set or edge.target not in node_set:
            raise HkgLifecycleError(f"HKG edge has a missing endpoint: {edge.edge_id}")
    elements: list[HkgNode | HkgEdge] = [*graph.nodes, *graph.edges]
    for element in elements:
        if not element.provenance:
            element_id = element.node_id if isinstance(element, HkgNode) else element.edge_id
            raise HkgLifecycleError(f"HKG element has no provenance: {element_id}")
        for provenance in element.provenance:
            indexed_artifact = artifacts.get((provenance.source_id, provenance.artifact_id))
            if indexed_artifact is None:
                raise HkgLifecycleError(
                    f"HKG provenance references an unknown source artifact: "
                    f"{provenance.source_id}:{provenance.artifact_id}"
                )
            if (
                provenance.path != indexed_artifact.relative_path
                or provenance.schema_version != indexed_artifact.schema_version
                or provenance.content_sha256 != indexed_artifact.sha256
            ):
                raise HkgLifecycleError(
                    f"HKG provenance does not match source index: "
                    f"{provenance.source_id}:{provenance.artifact_id}"
                )


def merge_graphs(existing: HkgGraph, incoming: HkgGraph) -> HkgGraph:
    source_by_id = {source.source_id: source for source in existing.sources}
    for source in incoming.sources:
        prior_source = source_by_id.get(source.source_id)
        if prior_source is not None and prior_source != source:
            raise HkgConflictError(f"source identity/content conflict: {source.source_id}")
        source_by_id[source.source_id] = source

    nodes = {node.node_id: node.model_copy(deep=True) for node in existing.nodes}
    for node in incoming.nodes:
        prior_node = nodes.get(node.node_id)
        if prior_node is None:
            nodes[node.node_id] = node.model_copy(deep=True)
        else:
            _merge_node(prior_node, node)
    edges = {edge.edge_id: edge.model_copy(deep=True) for edge in existing.edges}
    for edge in incoming.edges:
        prior_edge = edges.get(edge.edge_id)
        if prior_edge is None:
            edges[edge.edge_id] = edge.model_copy(deep=True)
        else:
            _merge_edge(prior_edge, edge)
    graph = _finalize_graph(
        sources=list(source_by_id.values()),
        nodes=list(nodes.values()),
        edges=list(edges.values()),
        warnings=sorted(set(existing.warnings) | set(incoming.warnings)),
    )
    return _recompute_canonical_clusters(graph)


def serialize_manifest(manifest: HkgStoreManifest) -> str:
    return json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def _load_inputs(
    failure_runs: Iterable[Path],
    failure_packages: Iterable[Path],
    mvp_demos: Iterable[Path],
) -> list[HkgSourcePayload]:
    payloads: list[HkgSourcePayload] = []
    try:
        payloads.extend(load_failure_run_source(path) for path in failure_runs)
        payloads.extend(load_failure_package_source(path) for path in failure_packages)
        for path in mvp_demos:
            payloads.extend(load_mvp_demo_sources(path))
    except (HkgSourceError, HkgBuildError) as exc:
        raise HkgLifecycleError(str(exc)) from exc
    if not payloads:
        raise HkgLifecycleError("at least one HKG source input is required")
    return payloads


def _normalize_payloads(
    payloads: list[HkgSourcePayload],
) -> tuple[list[HkgSourceRecord], list[FailureBundle]]:
    records: dict[str, HkgSourceRecord] = {}
    bundles: list[FailureBundle] = []
    for payload in sorted(payloads, key=lambda item: item.record.source_id):
        prior = records.get(payload.record.source_id)
        if prior is not None and prior != payload.record:
            raise HkgConflictError(f"source identity/content conflict: {payload.record.source_id}")
        records[payload.record.source_id] = payload.record
        bundles.append(payload.bundle)
    return [records[key] for key in sorted(records)], bundles


def _persist(root: Path, graph: HkgGraph) -> str:
    root.mkdir(parents=True, exist_ok=True)
    graph_path = root / HKG_GRAPH_FILENAME
    manifest_path = root / HKG_MANIFEST_FILENAME
    graph_bytes = serialize_graph(graph).encode("utf-8")
    graph_sha = sha256(graph_bytes).hexdigest()
    manifest = HkgStoreManifest(
        graph_schema_version=graph.schema_version,
        graph_id=graph.graph_id,
        graph_sha256=graph_sha,
        node_count=graph.node_count,
        edge_count=graph.edge_count,
        source_count=len(graph.sources),
        sources=graph.sources,
    )
    manifest_bytes = serialize_manifest(manifest).encode("utf-8")
    old_graph = graph_path.read_bytes() if graph_path.is_file() else None
    old_manifest = manifest_path.read_bytes() if manifest_path.is_file() else None
    try:
        _atomic_replace(graph_path, graph_bytes)
        _atomic_replace(manifest_path, manifest_bytes)
    except OSError as exc:
        try:
            _restore(graph_path, old_graph)
            _restore(manifest_path, old_manifest)
        except OSError as restore_exc:
            raise HkgLifecycleError(
                f"HKG write failed and prior store restoration failed: {restore_exc}"
            ) from exc
        raise HkgLifecycleError(f"HKG atomic write failed: {exc}") from exc
    return graph_sha


def _atomic_replace(path: Path, content: bytes) -> None:
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _restore(path: Path, content: bytes | None) -> None:
    if content is None:
        path.unlink(missing_ok=True)
    else:
        _atomic_replace(path, content)


def _recompute_canonical_clusters(graph: HkgGraph) -> HkgGraph:
    nodes = [
        node.model_copy(deep=True) for node in graph.nodes if node.type != NodeType.FAILURE_CLUSTER
    ]
    edges = [
        edge.model_copy(deep=True)
        for edge in graph.edges
        if edge.type != EdgeType.BELONGS_TO_CLUSTER
        and edge.source
        not in {node.node_id for node in graph.nodes if node.type == NodeType.FAILURE_CLUSTER}
        and edge.target
        not in {node.node_id for node in graph.nodes if node.type == NodeType.FAILURE_CLUSTER}
    ]
    node_by_id = {node.node_id: node for node in nodes}
    members: dict[str, list[str]] = {}
    fingerprint_edges: dict[tuple[str, str], HkgEdge] = {}
    for edge in edges:
        if edge.type == EdgeType.REFERENCES and edge.attributes.get("role") == "fingerprint":
            source = node_by_id.get(edge.source)
            target = node_by_id.get(edge.target)
            if source is not None and target is not None and source.type == NodeType.FAILURE:
                members.setdefault(target.node_id, []).append(source.node_id)
                fingerprint_edges[(source.node_id, target.node_id)] = edge
    for canonical_id in sorted(members):
        canonical = node_by_id[canonical_id]
        digest = canonical.attributes.get("canonical_digest", canonical.label)
        cluster_label = f"cluster-{digest[:16]}"
        cluster_id = semantic_node_id(NodeType.FAILURE_CLUSTER, cluster_label)
        provenance = _merge_provenance_lists(
            canonical.provenance,
            *[
                fingerprint_edges[(failure_id, canonical_id)].provenance
                for failure_id in sorted(members[canonical_id])
            ],
        )
        nodes.append(
            HkgNode(
                node_id=cluster_id,
                type=NodeType.FAILURE_CLUSTER,
                label=cluster_label,
                attributes={
                    "canonical_digest": digest,
                    "insufficient": "False",
                    "size": str(len(set(members[canonical_id]))),
                },
                provenance=provenance,
            )
        )
        for failure_id in sorted(set(members[canonical_id])):
            edges.append(
                HkgEdge(
                    edge_id=edge_id(EdgeType.BELONGS_TO_CLUSTER, failure_id, cluster_id),
                    type=EdgeType.BELONGS_TO_CLUSTER,
                    source=failure_id,
                    target=cluster_id,
                    provenance=provenance,
                )
            )
        edges.append(
            HkgEdge(
                edge_id=edge_id(EdgeType.BELONGS_TO_CLUSTER, canonical_id, cluster_id),
                type=EdgeType.BELONGS_TO_CLUSTER,
                source=canonical_id,
                target=cluster_id,
                provenance=provenance,
            )
        )
    return _finalize_graph(
        sources=graph.sources,
        nodes=nodes,
        edges=edges,
        warnings=graph.warnings,
    )


def _finalize_graph(
    *,
    sources: list[HkgSourceRecord],
    nodes: list[HkgNode],
    edges: list[HkgEdge],
    warnings: list[str],
) -> HkgGraph:
    for node in nodes:
        node.attributes = dict(sorted(node.attributes.items()))
        node.provenance = _merge_provenance_lists(node.provenance)
    for edge in edges:
        edge.attributes = dict(sorted(edge.attributes.items()))
        edge.provenance = _merge_provenance_lists(edge.provenance)
    ordered_nodes = sorted(nodes, key=lambda node: node.node_id)
    ordered_edges = sorted(edges, key=lambda edge: edge.edge_id)
    return HkgGraph(
        graph_id=PERSISTENT_GRAPH_ID,
        node_count=len(ordered_nodes),
        edge_count=len(ordered_edges),
        node_type_counts=_counts(str(node.type) for node in ordered_nodes),
        edge_type_counts=_counts(str(edge.type) for edge in ordered_edges),
        sources=sorted(sources, key=lambda source: source.source_id),
        nodes=ordered_nodes,
        edges=ordered_edges,
        warnings=sorted(set(warnings)),
        parser_notes=[
            "Persistent HKG v1 is assembled only from validated, hash-indexed structured sources.",
            "Occurrence identities are source-scoped; canonical fingerprints remain semantic.",
        ],
    )


def _merge_node(prior: HkgNode, incoming: HkgNode) -> None:
    if (
        prior.type != incoming.type
        or prior.label != incoming.label
        or prior.attributes != incoming.attributes
    ):
        raise HkgConflictError(f"incompatible node collision: {prior.node_id}")
    prior.provenance = _merge_provenance_lists(prior.provenance, incoming.provenance)


def _merge_edge(prior: HkgEdge, incoming: HkgEdge) -> None:
    if (
        prior.type != incoming.type
        or prior.source != incoming.source
        or prior.target != incoming.target
        or prior.attributes != incoming.attributes
    ):
        raise HkgConflictError(f"incompatible edge collision: {prior.edge_id}")
    prior.provenance = _merge_provenance_lists(prior.provenance, incoming.provenance)


def _merge_provenance_lists(*groups: list[Provenance]) -> list[Provenance]:
    unique = {
        (
            item.source_id,
            item.artifact_id,
            item.path,
            item.content_sha256,
            item.schema_version,
        ): item
        for group in groups
        for item in group
    }
    return [
        unique[key]
        for key in sorted(
            unique, key=lambda item: tuple("" if part is None else str(part) for part in item)
        )
    ]


def _summary(
    operation: HkgOperation,
    graph: HkgGraph,
    root: Path,
    graph_sha: str,
    *,
    changed: bool,
    added: list[str],
    existing: list[str],
) -> HkgOperationSummary:
    counts = _semantic_counts(graph)
    return HkgOperationSummary(
        operation=operation,
        changed=changed,
        graph_root=root,
        graph_sha256=graph_sha,
        source_count=len(graph.sources),
        node_count=graph.node_count,
        edge_count=graph.edge_count,
        canonical_failure_count=counts["canonical_fingerprint"],
        intervention_count=counts["intervention"],
        experiment_count=counts["experiment"],
        observed_effect_count=counts["observed_effect"],
        added_source_ids=sorted(added),
        existing_source_ids=sorted(existing),
    )


def _semantic_counts(graph: HkgGraph) -> dict[str, int]:
    return {
        "canonical_fingerprint": graph.node_type_counts.get("canonical_fingerprint", 0),
        "intervention": graph.node_type_counts.get("intervention", 0),
        "experiment": graph.node_type_counts.get("experiment", 0),
        "observed_effect": graph.node_type_counts.get("observed_effect", 0),
    }


def _counts(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _store_root(path: Path) -> Path:
    resolved = path.resolve()
    return resolved.parent if resolved.name == HKG_GRAPH_FILENAME else resolved


def _safe_relative(path: str) -> bool:
    pure = PurePosixPath(path)
    return bool(path) and not pure.is_absolute() and ".." not in pure.parts


def _raw_schema_version(path: Path) -> int | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    value = raw.get("schema_version") if isinstance(raw, dict) else None
    return value if isinstance(value, int) else None
