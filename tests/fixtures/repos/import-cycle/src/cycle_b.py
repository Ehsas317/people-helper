"""Cycle B — imports cycle_a (back-reference creating an SCC).

This file is the second half of a 2-file import cycle. Combined with
cycle_a.py, it forms a non-trivial strongly-connected component that
should be flagged by Tarjan's algorithm but missed by naive
"internal_imports >= 2" detection.
"""
from .cycle_a import helper_a


def helper_b(x: int) -> int:
    """A helper that calls A — completing the cycle.

    Subtracts 1 from whatever helper_a returns.
    """
    if x < 0:
        return 0
    return helper_a(x) - 1


def helper_b_squared(x: int) -> int:
    """Squared variant. Also calls helper_a."""
    if x > 50:
        return helper_b(x)
    return helper_a(x) ** 2
