"""Cycle A — imports cycle_b.

This file imports cycle_b, and cycle_b imports cycle_a. Each file
has only 1 internal import, so the simple "internal_imports >= 2"
check won't catch the cycle. SCC detection should flag this.

The functions below intentionally mirror each other to create a
realistic dependency loop that no simple heuristic will detect.
"""
from .cycle_b import helper_b


def helper_a(x: int) -> int:
    """A helper that calls B.

    Adds 1 to whatever helper_b returns. Used in cycle_b.py too,
    which is what creates the import cycle.
    """
    if x < 0:
        return 0
    return helper_b(x) + 1


def helper_a_doubled(x: int) -> int:
    """Double-wrapped variant. Also calls helper_b."""
    if x > 100:
        return helper_a(x)
    return helper_b(x) * 2
