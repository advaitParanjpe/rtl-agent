from __future__ import annotations

from collections.abc import Callable

from rtl_agent.reduction_models import TerminationReason


class BudgetExhausted(Exception):
    """Raised by an oracle when a new (uncached) evaluation would exceed the budget."""


def ddmin(
    item_ids: list[str], oracle: Callable[[list[str]], bool]
) -> tuple[list[str], TerminationReason]:
    """Deterministic delta-debugging (ddmin) reduction by whole-item removal.

    ``oracle(retained_ids)`` returns True when the retained subset still preserves
    the property of interest (here, the same observed failure family). Items are
    only removed (never mutated) and the relative order of retained items is
    preserved. The candidate ordering is deterministic: coarse chunks are tried
    in order, then granularity is increased. The oracle may raise
    ``BudgetExhausted`` to stop early; the best subset found so far is returned.
    """

    current = list(item_ids)
    granularity = 2
    try:
        while len(current) >= 2:
            chunk_size = -(-len(current) // granularity)  # ceil division
            chunks = [current[i : i + chunk_size] for i in range(0, len(current), chunk_size)]
            reduced = False
            for chunk in chunks:
                chunk_set = set(chunk)
                complement = [item for item in current if item not in chunk_set]
                if not complement:
                    continue
                if oracle(complement):
                    current = complement
                    granularity = max(granularity - 1, 2)
                    reduced = True
                    break
            if not reduced:
                if granularity >= len(current):
                    break
                granularity = min(len(current), granularity * 2)
        return current, TerminationReason.NO_FURTHER_REDUCTION
    except BudgetExhausted:
        return current, TerminationReason.BUDGET_EXHAUSTED
