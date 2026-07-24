"""Tests for people_helper.scoring — score formula + ship-effort."""

from people_helper.models import Candidate, SimilarProject
from people_helper.scoring import (
    _compute_code_quality,
    _compute_demand_signal,
    _compute_ship_effort,
    _compute_uniqueness,
    score_candidate,
)

# ===== Pure-function property tests =====

class TestComputeUniqueness:
    def test_zero_results_returns_high(self):
        assert _compute_uniqueness(0) == 8.0

    def test_one_two_results(self):
        assert _compute_uniqueness(1) == 6.0
        assert _compute_uniqueness(2) == 6.0

    def test_three_to_five(self):
        assert _compute_uniqueness(3) == 4.0
        assert _compute_uniqueness(5) == 4.0

    def test_six_plus(self):
        assert _compute_uniqueness(6) == 2.0
        assert _compute_uniqueness(100) == 2.0

    def test_monotonic_non_increasing(self):
        scores = [_compute_uniqueness(n) for n in [0, 1, 2, 3, 5, 6, 10, 50]]
        for prev, cur in zip(scores, scores[1:]):
            assert cur <= prev, f"non-monotonic at {prev} -> {cur}"

    def test_bounded(self):
        for n in [0, 1, 5, 100, 10000]:
            s = _compute_uniqueness(n)
            assert 2.0 <= s <= 8.0


class TestComputeShipEffort:
    def test_tiny(self):
        assert _compute_ship_effort(10) == 1.5

    def test_medium(self):
        assert _compute_ship_effort(100) == 3.0

    def test_large(self):
        assert _compute_ship_effort(200) == 6.0

    def test_xl(self):
        assert _compute_ship_effort(400) == 16.0

    def test_huge(self):
        # Above the largest bracket
        assert _compute_ship_effort(1000) == 16.0

    def test_monotonic_non_decreasing(self):
        efforts = [_compute_ship_effort(loc) for loc in [1, 30, 49, 50, 100, 149, 150, 250, 299, 300, 499, 500]]
        for prev, cur in zip(efforts, efforts[1:]):
            assert cur >= prev, f"non-monotonic at loc={prev} -> {cur}"


class TestComputeCodeQuality:
    def _make(self, **kw):
        defaults = dict(
            path="x.py", language="Python", loc=50,
            has_tests=True, has_docstring=True,
            internal_imports=0, external_imports=1,
            filename_score=0.5,
        )
        defaults.update(kw)
        return Candidate(**defaults)

    def test_perfect_candidate_caps_at_10(self):
        c = self._make()
        # tests(3) + docstring(2) + zero internal(2) + few external(2) + util name(1) = 10
        score = _compute_code_quality(c)
        assert score == 10.0

    def test_no_tests_no_docstring(self):
        c = self._make(has_tests=False, has_docstring=False)
        score = _compute_code_quality(c)
        # zero internal(2) + few external(2) + util name(1) = 5
        assert score == 5.0

    def test_bounded_0_to_10(self):
        for has_tests in [True, False]:
            for has_doc in [True, False]:
                for ii in [0, 1, 5]:
                    for ei in [1, 4, 10]:
                        c = self._make(
                            has_tests=has_tests, has_docstring=has_doc,
                            internal_imports=ii, external_imports=ei,
                        )
                        s = _compute_code_quality(c)
                        assert 0.0 <= s <= 10.0


class TestComputeDemandSignal:
    def test_empty_similar_returns_default_5(self):
        c = Candidate(
            path="x.py", language="Python", loc=50,
            has_tests=False, has_docstring=False,
            internal_imports=0, external_imports=0,
            filename_score=0.0,
            similar_projects=[],
        )
        assert _compute_demand_signal(c) == 5.0

    def test_high_star_project_boosts(self):
        c = Candidate(
            path="x.py", language="Python", loc=50,
            has_tests=False, has_docstring=False,
            internal_imports=0, external_imports=0,
            filename_score=0.0,
            similar_projects=[
                SimilarProject(
                    full_name="a/b", html_url="x", stars=5000,
                    description="", pushed_at="2026-01-01",
                    license="MIT", open_issues=10, forks=200,
                )
            ],
        )
        s = _compute_demand_signal(c)
        assert s > 5.0, f"high-star should boost signal above 5.0, got {s}"
        assert s <= 10.0

    def test_bounded_0_to_10(self):
        for stars in [0, 10, 100, 1000, 10000]:
            for forks in [0, 10, 100, 1000]:
                for issues in [0, 5, 50, 500]:
                    c = Candidate(
                        path="x.py", language="Python", loc=50,
                        has_tests=False, has_docstring=False,
                        internal_imports=0, external_imports=0,
                        filename_score=0.0,
                        similar_projects=[
                            SimilarProject(
                                full_name="a/b", html_url="x", stars=stars,
                                description="", pushed_at="2026-01-01",
                                license="MIT", open_issues=issues, forks=forks,
                            )
                        ],
                    )
                    s = _compute_demand_signal(c)
                    assert 0.0 <= s <= 10.0


class TestScoreCandidateIntegration:
    def test_combined_score_bounded(self):
        c = Candidate(
            path="x.py", language="Python", loc=100,
            has_tests=True, has_docstring=True,
            internal_imports=0, external_imports=1,
            filename_score=0.5,
        )
        score_candidate(c, similar_count=0)
        assert 0.0 <= c.combined_score <= 10.0
        # weight sum: 0.5 + 0.3 + 0.2 = 1.0
        # so combined_score = weighted avg of the 3 sub-scores (each 0-10)
        assert c.code_quality > 0
        assert c.uniqueness > 0
        # demand_signal defaults to 5.0 with no similar_projects
        assert c.demand_signal == 5.0

    def test_weights_sum_to_one(self):
        # Combined score formula: 0.5*cq + 0.3*uq + 0.2*ds
        c = Candidate(
            path="x.py", language="Python", loc=50,
            has_tests=True, has_docstring=True,
            internal_imports=0, external_imports=1,
            filename_score=0.5,
        )
        score_candidate(c, similar_count=2)
        expected = 0.5 * c.code_quality + 0.3 * c.uniqueness + 0.2 * c.demand_signal
        assert abs(c.combined_score - expected) < 0.001
