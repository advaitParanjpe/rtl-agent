"""Stable identity helpers for persistent HKG entities.

Occurrence-specific entities are scoped to a validated source ID. Semantic
canonical fingerprints and observed-effect labels remain global. All escaping
is deterministic and independent of source location.
"""

from __future__ import annotations

from urllib.parse import quote

from rtl_agent.hkg.models import EdgeType, NodeType


def failure_source_id(run_id: str) -> str:
    return f"failure-run:{run_id}"


def mvp_source_id(target_commit: str | None, demo_id: str) -> str:
    return f"mvp:{target_commit or 'uncommitted'}:{demo_id}"


def scoped_node_id(node_type: NodeType, source_id: str, key: str) -> str:
    return f"{node_type}:{_part(source_id)}:{_part(key)}"


def semantic_node_id(node_type: NodeType, key: str) -> str:
    return f"{node_type}:{_part(key)}"


def edge_id(edge_type: EdgeType, source: str, target: str, role: str = "") -> str:
    return f"{edge_type}|{source}|{target}|{_part(role)}"


def _part(value: str) -> str:
    return quote(value, safe="-._~")
