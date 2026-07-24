"""Tests for people_helper.search — GitHub search query building + differentiators."""
from datetime import datetime, timedelta, timezone

from people_helper.models import Candidate, SimilarProject
from people_helper.search import (
    build_search_query,
    compute_differentiators,
    github_search_repositories,
)


class TestBuildSearchQuery:
    def _cand(self, path: str, docstring: str = "") -> Candidate:
        return Candidate(
            path=path, language="Python", loc=50,
            has_tests=False, has_docstring=bool(docstring),
            internal_imports=0, external_imports=0,
            filename_score=0.0,
            docstring_snippet=docstring,
        )

    def test_uses_stem(self):
        c = self._cand("src/string_utils.py")
        q = build_search_query(c)
        assert "string_utils" in q or "string" in q

    def test_filters_noise_words(self):
        c = self._cand(
            "src/foo.py",
            docstring="the module for the function",
        )
        q = build_search_query(c)
        # Noise words should not be in query
        for noise in ["the", "module", "for", "function"]:
            # the noise word could appear as substring of a real word,
            # so check as whole word
            parts = q.split()
            assert noise not in parts, f"'{noise}' should be filtered, q={q}"


class TestComputeDifferentiators:
    def _cand(self, similar: list) -> Candidate:
        c = Candidate(
            path="x.py", language="Python", loc=50,
            has_tests=True, has_docstring=True,
            internal_imports=0, external_imports=0,
            filename_score=0.0,
            similar_projects=similar,
        )
        return c

    def test_no_similar_projects_first_mover(self):
        c = self._cand([])
        diffs = compute_differentiators(c)
        assert any("first-mover" in d.lower() or "underserved" in d.lower() or "no similar" in d.lower() for d in diffs)

    def test_top_high_stars_competitive(self):
        c = self._cand([
            SimilarProject(
                full_name="a/popular", html_url="x", stars=2000,
                description="", pushed_at="2026-01-01",
                license="MIT", open_issues=10, forks=200, language="Python",
            )
        ])
        diffs = compute_differentiators(c)
        assert any("stars" in d.lower() for d in diffs)

    def test_top_low_stars_underserved(self):
        c = self._cand([
            SimilarProject(
                full_name="a/unpopular", html_url="x", stars=20,
                description="", pushed_at="2026-01-01",
                license="MIT", open_issues=2, forks=1, language="Python",
            )
        ])
        diffs = compute_differentiators(c)
        assert any("underserved" in d.lower() or "fill gaps" in d.lower() for d in diffs)

    def test_stale_top_project_opportunity(self):
        # 18 months stale
        old_date = (datetime.now(timezone.utc) - timedelta(days=540)).strftime("%Y-%m-%d")
        c = self._cand([
            SimilarProject(
                full_name="a/stale", html_url="x", stars=100,
                description="", pushed_at=old_date,
                license="MIT", open_issues=5, forks=10, language="Python",
            )
        ])
        diffs = compute_differentiators(c)
        assert any("maintenance" in d.lower() or "hasn't been pushed" in d.lower() for d in diffs)

    def test_active_top_project_warning(self):
        # 1 month ago
        recent_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
        c = self._cand([
            SimilarProject(
                full_name="a/active", html_url="x", stars=100,
                description="", pushed_at=recent_date,
                license="MIT", open_issues=5, forks=10, language="Python",
            )
        ])
        diffs = compute_differentiators(c)
        assert any("actively maintained" in d.lower() or "study" in d.lower() for d in diffs)

    def test_tests_vs_open_issues(self):
        c = self._cand([
            SimilarProject(
                full_name="a/buggy", html_url="x", stars=100,
                description="", pushed_at="2026-01-01",
                license="MIT", open_issues=50, forks=10, language="Python",
            )
        ])
        # candidate has_tests=True, top has 50 open issues
        diffs = compute_differentiators(c)
        assert any("tests" in d.lower() or "reliability" in d.lower() for d in diffs)


class TestGithubSearchRepositoriesNetwork:
    """Network-mocked test: confirms the function gracefully handles
    a 403 / rate limit without raising."""

    def test_handles_403_gracefully(self, monkeypatch, capsys):
        # Mock httpx.get to return a 403
        import httpx

        from people_helper import search as search_mod

        class FakeResponse:
            status_code = 403
            def json(self):
                return {"message": "rate limited"}

        class FakeHttpx:
            HTTPError = httpx.HTTPError
            @staticmethod
            def get(*args, **kwargs):
                return FakeResponse()

        monkeypatch.setattr(search_mod, "httpx", FakeHttpx)

        result = github_search_repositories(
            "test query", "Python", "fake-pat", min_stars=5
        )
        assert result == []
        captured = capsys.readouterr()
        assert "rate" in captured.err.lower() or "warn" in captured.err.lower()
