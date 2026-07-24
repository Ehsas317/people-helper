"""orphan.py — a leaf with no incoming imports and no outgoing imports.

This file is the ideal extraction target: zero internal imports, zero
external dependencies, has a docstring, and nothing else in the project
imports it (fan-in == 0). The reverse-import index should mark it
orphan → strong extractable signal.
"""


def levenshtein(a: str, b: str) -> int:
    """Compute the Levenshtein edit distance between two strings.

    Uses the Wagner-Fischer dynamic programming algorithm. Runs in
    O(len(a) * len(b)) time and O(min(len(a), len(b))) space.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    if len(a) < len(b):
        a, b = b, a

    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            insert = previous[j] + 1
            delete = current[j - 1] + 1
            substitute = previous[j - 1] + (ca != cb)
            current.append(min(insert, delete, substitute))
        previous = current

    return previous[-1]
