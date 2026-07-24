"""Stage 6: Scoring.

Formula: combined = 0.5 * code_quality + 0.3 * uniqueness + 0.2 * demand_signal

- code_quality: how well-written and self-contained the code is (0-10)
- uniqueness: how rare similar projects are on GitHub (0-10)
- demand_signal: how much interest exists for this type of tool (0-10)

New in v0.3:
- code_quality now applies a complexity penalty (god functions get dinged).
- code_quality now applies an orphan boost (fan-in == 0 is a great signal).
- code_quality now applies a cycle penalty.
"""

from .config import (
    CODE_QUALITY_WEIGHT,
    DEMAND_SIGNAL_WEIGHT,
    SHIP_EFFORT_BRACKETS,
    UNIQUENESS_WEIGHT,
)


def _compute_code_quality(cand) -> float:
    """
    Score how ready the code is for open source.
    Tests, docs, independence, small dep footprint.
    Penalties: high cyclomatic complexity, import cycles.
    Boosts: zero fan-in (orphan), low complexity.
    """
    score = 0.0
    if cand.has_tests:
        score += 3
    if cand.has_docstring:
        score += 2
    if cand.internal_imports == 0:
        score += 2
    elif cand.internal_imports == 1:
        score += 1
    if cand.external_imports <= 3:
        score += 2
    elif cand.external_imports <= 5:
        score += 1
    if cand.filename_score > 0:
        score += 1

    # --- New v0.3 signals ---
    # Orphan boost: zero fan-in means nothing else in the repo depends on it,
    # so it's safe to lift out without breaking anything. This is the ideal
    # extraction target. Only applies when we actually computed fan-in.
    if cand.fan_in == 0:
        score += 1.0

    # Complexity penalty: god functions are hard to extract cleanly.
    # cc <= 5 → no penalty. cc 6-10 → -0.5. cc 11-20 → -1.5. cc > 20 → -3.0.
    if cand.complexity > 20:
        score -= 3.0
    elif cand.complexity > 10:
        score -= 1.5
    elif cand.complexity > 5:
        score -= 0.5

    # Cycle penalty: a file in an import SCC requires breaking the cycle
    # before extraction. Strong signal that it's not actually self-contained.
    if cand.in_cycle:
        score -= 1.5

    return max(0.0, min(score, 10.0))


def _compute_uniqueness(similar_count: int) -> float:
    """
    Score based on how many similar projects exist.
    Fewer = more unique = higher score.
    """
    if similar_count == 0:
        return 8.0
    elif similar_count <= 2:
        return 6.0
    elif similar_count <= 5:
        return 4.0
    else:
        return 2.0


def _compute_demand_signal(cand) -> float:
    """
    Score based on whether there's actual demand for this type of tool.
    Uses data from similar projects found on GitHub.
    Higher stars and more forks on similar projects = more demand.
    If no similar projects found, moderate demand is assumed (niche but real).
    """
    if not cand.similar_projects:
        # No similar projects found — niche space, moderate assumed demand
        return 5.0

    # Weighted by position (top result matters most)
    total_signal = 0.0
    weight_sum = 0.0
    for i, proj in enumerate(cand.similar_projects):
        # Weight decreases with rank
        weight = 1.0 / (i + 1)
        # Stars signal (log scale to avoid dominance by mega-projects)
        star_signal = min(10.0, proj.stars / 100.0) if proj.stars > 0 else 0.0
        # Fork signal (indicates actual usage)
        fork_signal = min(5.0, proj.forks / 50.0) if proj.forks > 0 else 0.0
        # Open issues signal (indicates user engagement)
        issue_signal = min(3.0, proj.open_issues / 10.0) if proj.open_issues > 0 else 0.0

        # New v0.3: stars-per-fork ratio (engagement quality).
        # High stars but low forks = vanity / curiosity, not real use.
        # Low stars but high forks = real fork-and-extend usage.
        if proj.stars > 0 and proj.forks > 0:
            ratio = proj.stars / proj.forks
            if ratio > 50:  # lots of stargazers, few forks → hype
                ratio_signal = 0.0
            elif ratio < 5:  # lots of forks relative to stars → real usage
                ratio_signal = 1.5
            else:
                ratio_signal = 0.5
        else:
            ratio_signal = 0.0

        total_signal += weight * (star_signal + fork_signal + issue_signal + ratio_signal)
        weight_sum += weight

    avg_signal = total_signal / weight_sum if weight_sum > 0 else 0
    # Normalize to 0-10
    return min(10.0, avg_signal / 1.8)


def _compute_ship_effort(loc: int) -> float:
    """Estimate hours to ship based on LOC."""
    for threshold, hours in SHIP_EFFORT_BRACKETS:
        if loc < threshold:
            return hours
    return SHIP_EFFORT_BRACKETS[-1][1]


def score_candidate(cand, similar_count: int) -> None:
    """
    Score a candidate in-place using the formula:
    combined = 0.5 * code_quality + 0.3 * uniqueness + 0.2 * demand_signal
    """
    cand.code_quality = _compute_code_quality(cand)
    cand.uniqueness = _compute_uniqueness(similar_count)
    cand.demand_signal = _compute_demand_signal(cand)
    cand.ship_effort_hours = _compute_ship_effort(cand.loc)

    cand.combined_score = (
        CODE_QUALITY_WEIGHT * cand.code_quality
        + UNIQUENESS_WEIGHT * cand.uniqueness
        + DEMAND_SIGNAL_WEIGHT * cand.demand_signal
    )
