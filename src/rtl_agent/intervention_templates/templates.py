"""Pure, deterministic derivation of bounded edits from driver evidence.

Each function takes already-extracted textual evidence and returns a single
`(old, new)` textual replacement, or ``None`` when the evidence cannot support a
safe, syntactically bounded edit. No filesystem or model access here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_NONBLOCKING_RE = re.compile(r"^(?P<lhs>.+?)\s*<=\s*(?P<rhs>.+?)\s*;\s*$")
_CONTINUOUS_RE = re.compile(r"^assign\s+(?P<lhs>.+?)\s*=\s*(?P<rhs>.+?)\s*;\s*$")
_BLOCKING_RE = re.compile(r"^(?P<lhs>.+?)\s*=\s*(?P<rhs>.+?)\s*;\s*$")
_GUARD_RE = re.compile(r"if\s*\((?P<expr>.+)\)\s*(?:begin\b.*)?$")
_CONSTANT_RE = re.compile(r"^(?:[0-9]+'[bdh][0-9a-fA-FxzXZ_]+|'[01xzXZ]|[0-9]+)$")


@dataclass(frozen=True)
class Assignment:
    lhs: str
    rhs: str
    operator: str  # "<=", "=", or "assign="


def parse_assignment(statement_text: str, statement_kind: str) -> Assignment | None:
    text = statement_text.strip()
    if statement_kind == "continuous_assign":
        match = _CONTINUOUS_RE.match(text)
        if match:
            return Assignment(match.group("lhs").strip(), match.group("rhs").strip(), "assign=")
        return None
    if statement_kind == "procedural_assign":
        match = _NONBLOCKING_RE.match(text)
        if match:
            return Assignment(match.group("lhs").strip(), match.group("rhs").strip(), "<=")
        match = _BLOCKING_RE.match(text)
        if match and not text.startswith("assign"):
            return Assignment(match.group("lhs").strip(), match.group("rhs").strip(), "=")
    return None


def suppress_edit(statement_text: str, assignment: Assignment) -> tuple[str, str] | None:
    """Neutralize an assignment by driving a benign zero instead of its value."""

    if assignment.rhs == "'0":
        return None
    if assignment.rhs.strip() == assignment.lhs.strip():
        return None  # already a self-hold; suppressing it is not a useful experiment
    new_rhs = "'0"
    return statement_text.strip(), _rebuild(statement_text, assignment, new_rhs)


def hold_edit(statement_text: str, assignment: Assignment) -> tuple[str, str] | None:
    """Hold the previous register value across a sequential update (lhs <= lhs)."""

    if assignment.operator != "<=":
        return None
    lhs_core = assignment.lhs.strip()
    if not re.fullmatch(r"[A-Za-z_]\w*", lhs_core):
        return None  # only simple whole-register holds are safe
    if assignment.rhs == lhs_core:
        return None
    return statement_text.strip(), _rebuild(statement_text, assignment, lhs_core)


def block_transition_edit(statement_text: str, assignment: Assignment) -> tuple[str, str] | None:
    """Block one constant next-state assignment by holding the register instead."""

    if assignment.operator != "<=":
        return None
    lhs_core = assignment.lhs.strip()
    if not re.fullmatch(r"[A-Za-z_]\w*", lhs_core):
        return None
    if not _CONSTANT_RE.match(assignment.rhs):
        return None  # only block clearly-constant transitions
    if assignment.rhs == lhs_core:
        return None
    return statement_text.strip(), _rebuild(statement_text, assignment, lhs_core)


def override_condition_edit(guard: str) -> tuple[str, str] | None:
    """Force one Boolean guard expression false (bounded constant override)."""

    expr = extract_guard_expression(guard)
    if expr is None:
        return None
    if _CONSTANT_RE.match(expr):
        return None  # already constant; nothing meaningful to override
    return expr, "1'b0"


def extract_guard_expression(guard: str | None) -> str | None:
    if not guard:
        return None
    match = _GUARD_RE.search(guard.strip())
    if not match:
        return None
    expr = match.group("expr").strip()
    # The greedy capture must yield a balanced, non-empty expression.
    if not expr or expr.count("(") != expr.count(")"):
        return None
    if len(expr) < 2:
        return None
    return expr


def _rebuild(statement_text: str, assignment: Assignment, new_rhs: str) -> str:
    text = statement_text.strip()
    op = "=" if assignment.operator == "assign=" else assignment.operator
    # Replace only the RHS token, preserving the surrounding operator spacing.
    idx = text.rfind(assignment.rhs + ";")
    if idx == -1:
        # Fall back to a canonical reconstruction.
        prefix = "assign " if assignment.operator == "assign=" else ""
        return f"{prefix}{assignment.lhs} {op} {new_rhs};"
    return text[:idx] + new_rhs + ";"
