'''Stage 6: Scoring with the new formula.

Formula: combined = 0.5 * code_quality + 0.3 * uniqueness + 0.2 * demand_signal

- code_quality: how well-written and self-contained the code is (0-10)
- uniqueness: how rare similar projects are on GitHub (0-10)
- demand_signal: how much interest exists for this type of tool (0-10)
'''

from .config import (
    CODE_QUALITY_WEIGHT,
    UNIQUENESS_WEIGHT,
    DEMAND_SIGNAL_WEIGHT,
    SHIP_EFFORT_BRACKETS,
)


def _compute_code_quality(cand) -> float:
    """
    Score how ready the code is for open source.
    Tests, docs, independence, small dep footprint.
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
    return min(score, 10.0)


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

        total_signal += weight * (star_signal + fork_signal + issue_signal)
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
    Score a candidate in-place using the new formula:
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
