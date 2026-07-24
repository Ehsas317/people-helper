"""Tests for people_helper.report — markdown report generation."""

from people_helper.models import Candidate, SimilarProject
from people_helper.report import generate_report


def _cand(**kw) -> Candidate:
    defaults = dict(
        path="src/foo.py", language="Python", loc=50,
        has_tests=True, has_docstring=True,
        internal_imports=0, external_imports=1,
        filename_score=0.5,
        code_quality=8.0,
        uniqueness=6.0,
        demand_signal=5.0,
        ship_effort_hours=1.5,
        combined_score=6.7,
        what_it_does="A useful utility for foos.",
        why_extractable=["Has tests", "Has docstring", "Zero internal imports"],
        docstring_snippet='"""Module docstring."""',
        first_lines='"""Module docstring."""\n\n\ndef foo():\n    pass\n',
        suggested_name="foo-utils",
        suggested_tags=["python", "utility", "open-source"],
    )
    defaults.update(kw)
    return Candidate(**defaults)


class TestGenerateReport:
    def test_writes_file(self, tmp_path):
        out = tmp_path / "report.md"
        generate_report("owner", "repo", "Python", [], out)
        assert out.exists()
        text = out.read_text()
        assert "People Helper Report" in text
        assert "owner/repo" in text

    def test_includes_candidate_path(self, tmp_path):
        out = tmp_path / "report.md"
        c = _cand(path="src/string_utils.py")
        generate_report("owner", "repo", "Python", [c], out)
        text = out.read_text()
        assert "string_utils" in text

    def test_includes_scores(self, tmp_path):
        out = tmp_path / "report.md"
        c = _cand(code_quality=8.0, uniqueness=6.0, demand_signal=5.0, combined_score=6.7)
        generate_report("owner", "repo", "Python", [c], out)
        text = out.read_text()
        assert "6.7" in text
        assert "8" in text  # code quality
        assert "6" in text  # uniqueness

    def test_includes_similar_projects(self, tmp_path):
        out = tmp_path / "report.md"
        c = _cand(
            similar_projects=[
                SimilarProject(
                    full_name="a/popular", html_url="https://github.com/a/popular",
                    stars=1234, description="A popular lib",
                    pushed_at="2026-01-01", license="MIT",
                    open_issues=5, forks=20,
                )
            ]
        )
        generate_report("owner", "repo", "Python", [c], out)
        text = out.read_text()
        assert "a/popular" in text
        assert "1234" in text

    def test_handles_no_active_candidates(self, tmp_path):
        out = tmp_path / "report.md"
        c = _cand(skipped=True, skip_reason="too many internal imports")
        generate_report("owner", "repo", "Python", [c], out)
        text = out.read_text()
        assert "Skipped" in text or "skipped" in text
        assert "too many internal imports" in text

    def test_sorts_by_combined_score_desc(self, tmp_path):
        out = tmp_path / "report.md"
        c1 = _cand(path="src/low.py", combined_score=3.0)
        c2 = _cand(path="src/high.py", combined_score=9.0)
        c3 = _cand(path="src/mid.py", combined_score=6.0)
        generate_report("owner", "repo", "Python", [c1, c2, c3], out)
        text = out.read_text()
        # high should appear before mid, which appears before low
        high_pos = text.find("high.py")
        mid_pos = text.find("mid.py")
        low_pos = text.find("low.py")
        assert 0 < high_pos < mid_pos < low_pos

    def test_respects_max_candidates(self, tmp_path):
        out = tmp_path / "report.md"
        cands = [
            _cand(path=f"src/f{i}.py", combined_score=float(10 - i))
            for i in range(20)
        ]
        generate_report("owner", "repo", "Python", cands, out, max_candidates=5)
        text = out.read_text()
        # Should mention there are lower-ranked candidates
        assert "Lower-ranked" in text or "lower-ranked" in text.lower()
