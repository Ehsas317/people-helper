"""Stage 6: Scoring.

6 dimensions, all using pre-computed signals from detection:
  combined = 0.25*quality + 0.20*usefulness + 0.15*uniqueness
             + 0.15*relevance + 0.15*maintainability + 0.10*demand

Scoring functions use pre-computed fields from detection — they never
access raw file content.

Hard gate: if relevance < 3.0, combined is halved — a file that isn't
genuinely standalone can't be saved by good code quality alone.
"""

from pathlib import Path

from .config import (
    CODE_QUALITY_WEIGHT,
    DEMAND_SIGNAL_WEIGHT,
    MAINTAINABILITY_WEIGHT,
    RELEVANCE_WEIGHT,
    SHIP_EFFORT_BRACKETS,
    UNIQUENESS_WEIGHT,
    USEFULNESS_WEIGHT,
)


def _large_file_penalty(loc: int) -> float:
    """Soft penalty for files above the sweet spot (500 LOC).

    Returns a penalty in the range [0.0, 1.0] that scales linearly:
    - 500 LOC → 0.0 (no penalty, sweet spot ceiling)
    - 501-650 LOC → -0.1 (1 bracket over)
    - 651-800 LOC → -0.2
    - 801-950 LOC → -0.3
    - ...0.1 per 150 extra LOC
    - 2000 LOC → -1.0 (capped)

    Uses ceiling division to ensure even 1 LOC over 500 gets penalized.
    This replaces the old hard 500-LOC skip with a graduated penalty so large
    but genuinely standalone utilities can still be detected (just scored lower).
    """
    if loc <= 500:
        return 0.0
    overage = loc - 500
    # Ceiling division: (overage + 149) // 150 gives 1 for 1-150, 2 for 151-300, etc.
    brackets = (overage + 149) // 150
    return -min(1.0, brackets * 0.1)


def _compute_code_quality(cand) -> float:
    """Quality requires MULTIPLE positive signals, not just one.

    A file with just a docstring but no tests, no utility name, and high
    complexity should NOT score 6+. We start from 0 and only award points
    for genuinely quality signals.
    """
    score = 0.0
    # Tests are the strongest quality signal
    if cand.has_tests:
        score += 2.5
    if cand.has_docstring:
        score += 1.5
    if cand.internal_imports == 0:
        score += 1.5
    elif cand.internal_imports == 1:
        score += 0.5
    if cand.external_imports <= 3:
        score += 1.5
    elif cand.external_imports <= 5:
        score += 0.5
    if cand.filename_score > 0:
        score += 0.5
    # Fan-in: high inbound coupling is a strong negative signal
    if cand.fan_in == 0:
        score += 0.5
    elif cand.fan_in > 50:
        score -= 2.5
    elif cand.fan_in > 20:
        score -= 1.5
    elif cand.fan_in > 10:
        score -= 0.5
    # Extraction verification directly affects quality
    if cand.extraction_type == "single" and not cand.relative_imports:
        score += 1.0  # verified standalone = higher quality
    elif cand.extraction_type == "multi":
        score -= 1.0  # needs siblings = lower quality
    # Penalties
    if cand.complexity > 20:
        score -= 3.0
    elif cand.complexity > 10:
        score -= 1.5
    elif cand.complexity > 5:
        score -= 0.5
    if cand.in_cycle:
        score -= 2.0
    # No docstring AND no tests = -1.5 (mediocre)
    if not cand.has_docstring and not cand.has_tests:
        score -= 1.5
    # Excellent bonus: tests + docstring + low complexity
    if cand.has_tests and cand.has_docstring and 0 < cand.complexity <= 5:
        score += 1.0
    # Soft penalty for large files (replaces old hard 500-LOC skip)
    score -= _large_file_penalty(cand.loc)
    return max(0.0, min(score, 10.0))


def _compute_relevance(cand) -> float:
    """Is this genuinely standalone and reusable?

    Standalone-ness is the strongest signal. Quality signals (tests, docs,
    size) matter less here. Relevance is about CAN I extract this, not
    SHOULD I extract this.
    """
    score = 4.0  # Relevance must be earned
    # EXTRACTION VERIFICATION — the fundamental signal
    if cand.extraction_type == "single" and not cand.relative_imports:
        score += 2.5  # verified standalone — the gold standard
    elif cand.extraction_type == "multi":
        score -= 1.5  # needs siblings — less standalone, more coupling
    if cand.dependency_weight == 0:
        score += 2.0
    elif cand.dependency_weight == 1:
        score += 0.5
    elif cand.dependency_weight == 3:
        score -= 2.5
    if cand.api_surface_count >= 3:
        score += 1.5
    elif cand.api_surface_count == 2:
        score += 0.5
    elif cand.api_surface_count == 1:
        score -= 1.0
    elif cand.api_surface_count == 0:
        score -= 2.5
    if cand.has_project_specific_refs:
        score -= 2.0
    if 50 <= cand.loc <= 200:
        score += 0.5
    elif cand.loc < 20:
        score -= 1.5
    elif cand.loc > 400:
        score -= 0.5
    if cand.has_tests:
        score += 0.5
    if cand.has_docstring:
        score += 0.5
    if cand.internal_imports == 0:
        score += 0.5
    # Fan-in penalty in relevance: high inbound coupling = not standalone
    if cand.fan_in > 50:
        score -= 2.5
    elif cand.fan_in > 20:
        score -= 1.5
    elif cand.fan_in > 10:
        score -= 0.5
    # Legal signal — no license means extraction is risky
    if not cand.source_has_license:
        score -= 1.0
    return max(0.0, min(score, 10.0))


def _compute_usefulness(cand) -> float:
    """Is this solving a real, common problem?

    Usefulness requires either a generic function name OR a generic
    filename. A file with neither is project-specific, not useful.
    """
    score = 4.0  # Usefulness must be earned
    generic_patterns = [
        "slugify",
        "sanitize",
        "escape",
        "encode",
        "decode",
        "format",
        "parse",
        "validate",
        "convert",
        "transform",
        "compress",
        "decompress",
        "encrypt",
        "decrypt",
        "hash",
        "checksum",
        "sort",
        "filter",
        "search",
        "match",
        "replace",
        "split",
        "join",
        "merge",
        "cache",
        "memoize",
        "retry",
        "backoff",
        "timeout",
        "serialize",
        "deserialize",
        "case_insensitive",
        "levenshtein",
        "distance",
        "similarity",
    ]
    found_generic = False
    for name in cand.function_names:
        nl = name.lower()
        for pattern in generic_patterns:
            if pattern in nl:
                score += 1.5
                found_generic = True
                break
        if found_generic:
            break
    if not found_generic:
        for name in cand.function_names:
            if len(name) > 25 or name.count("_") > 3:
                score -= 1.0
                break
    stem = Path(cand.path).stem.lower()
    if stem in {
        "utils",
        "helpers",
        "common",
        "validators",
        "sanitizer",
        "parser",
        "formatter",
        "converter",
        "serializer",
        "cache",
        "retry",
        "auth",
        "crypto",
        "hash",
        "encode",
        "decode",
        "structures",
        "collections",
    }:
        score += 1.0
    if 50 <= cand.loc <= 300:
        score += 1.0
    elif cand.loc < 20:
        score -= 1.5
    if cand.has_tests:
        score += 0.5
    if cand.api_surface_count >= 3:
        score += 1.0
    elif cand.api_surface_count == 1:
        score -= 0.5
    if cand.is_stdlib_only:
        score += 0.5
    # No function names at all = -1.0 (not useful as a library)
    if cand.api_surface_count == 0:
        score -= 1.0
    return max(0.0, min(score, 10.0))


def _compute_maintainability(cand) -> float:
    """Is the code readable and maintainable?"""
    score = 4.0  # Maintainability must be earned
    if cand.comment_ratio >= 0.15:
        score += 2.0
    elif cand.comment_ratio >= 0.05:
        score += 1.0
    elif cand.comment_ratio == 0 and cand.loc > 30:
        score -= 1.5
    if cand.has_docstring:
        score += 1.0
    if cand.complexity > 0:
        if cand.complexity <= 5:
            score += 1.5
        elif cand.complexity <= 10:
            score += 0.5
        elif cand.complexity > 20:
            score -= 2.0
        elif cand.complexity > 15:
            score -= 1.0
    if 50 <= cand.loc <= 200:
        score += 1.0
    elif cand.loc > 400:
        score -= 0.5
    # Graduated penalty for large files: -0.1 per 150 LOC over 500.
    # No hard LOC ceiling in detection.py — this soft penalty lets large
    # but genuinely standalone files be detected, just with a lower score.
    # Examples: 501-650 LOC → -0.1, 651-800 → -0.2, 801-950 → -0.3, 2000 → -1.0
    # Consistent with _large_file_penalty() in code quality.
    if cand.loc > 500:
        penalty = _large_file_penalty(cand.loc)
        score += penalty
    if cand.has_tests:
        score += 0.5
    return max(0.0, min(score, 10.0))


def _compute_uniqueness(similar_count: int) -> float:
    """When --no-network mode is used, similar_count is passed as 0 by the
    caller. But that doesn't mean 'no similar projects exist' — it means
    'we didn't check'. Return a neutral score (5.0) for the unknown case
    so --no-network doesn't artificially inflate uniqueness.

    The caller distinguishes: network mode passes actual count (0 = truly
    unique), --no-network passes -1 to signal 'unknown'."""
    if similar_count < 0:
        return 5.0  # Unknown — neutral, neither boost nor penalty
    if similar_count == 0:
        return 8.0
    elif similar_count <= 2:
        return 6.0
    elif similar_count <= 5:
        return 4.0
    else:
        return 2.0


def _compute_demand_signal(cand) -> float:
    # Guard against RATE_LIMITED sentinel (string) or non-list types
    if not cand.similar_projects or not isinstance(cand.similar_projects, list):
        return 5.0
    total, weight_sum = 0.0, 0.0
    for i, proj in enumerate(cand.similar_projects):
        w = 1.0 / (i + 1)
        star_score = min(10.0, proj.stars / 100.0) if proj.stars > 0 else 0.0
        fork_score = min(5.0, proj.forks / 50.0) if proj.forks > 0 else 0.0
        issue_score = min(3.0, proj.open_issues / 10.0) if proj.open_issues > 0 else 0.0
        ratio_score = 0.0
        if proj.stars > 0 and proj.forks > 0:
            ratio = proj.stars / proj.forks
            ratio_score = 0.0 if ratio > 50 else (1.5 if ratio < 5 else 0.5)
        total += w * (star_score + fork_score + issue_score + ratio_score)
        weight_sum += w
    return min(10.0, (total / weight_sum if weight_sum > 0 else 0) / 1.8)


def _compute_ship_effort(loc: int) -> float:
    for threshold, hours in SHIP_EFFORT_BRACKETS:
        if loc < threshold:
            return hours
    return SHIP_EFFORT_BRACKETS[-1][1]


def score_candidate(cand, similar_count: int) -> None:
    cand.code_quality = _compute_code_quality(cand)
    cand.uniqueness = _compute_uniqueness(similar_count)
    cand.demand_signal = _compute_demand_signal(cand)
    cand.ship_effort_hours = _compute_ship_effort(cand.loc)
    cand.relevance = _compute_relevance(cand)
    cand.usefulness = _compute_usefulness(cand)
    cand.maintainability = _compute_maintainability(cand)
    raw = (
        CODE_QUALITY_WEIGHT * cand.code_quality
        + UNIQUENESS_WEIGHT * cand.uniqueness
        + DEMAND_SIGNAL_WEIGHT * cand.demand_signal
        + RELEVANCE_WEIGHT * cand.relevance
        + USEFULNESS_WEIGHT * cand.usefulness
        + MAINTAINABILITY_WEIGHT * cand.maintainability
    )
    if cand.relevance < 3.0:
        raw *= 0.5
    cand.combined_score = max(0.0, min(raw, 10.0))
