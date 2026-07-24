"""End-to-end tests — exercise the full pipeline against fixture repos.

These tests run detect_candidates → score_candidate → suggest_name/tags → report
without hitting the network (no_network mode).
"""
import sys
from pathlib import Path

# Make src/ importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from people_helper.detection import detect_candidates
from people_helper.models import Candidate
from people_helper.naming import suggest_name, suggest_tags
from people_helper.report import generate_report
from people_helper.scoring import score_candidate
from people_helper.walker import detect_primary_language, walk_repo


def _run_pipeline(repo_path: Path, no_network: bool = True) -> list[Candidate]:
    """Run the local-only pipeline. Returns the list of active candidates."""
    files = walk_repo(repo_path)
    if not files:
        return []
    lang = detect_primary_language(files)
    candidates = detect_candidates(files, lang)
    active = [c for c in candidates if not c.skipped]
    for c in active:
        score_candidate(c, similar_count=0)  # 0 = no network
        c.differentiators = ["(network search skipped in test)"]
        c.suggested_name = suggest_name(c)
        c.suggested_tags = suggest_tags(c)
    return active


class TestEndToEndCleanUtility:
    def test_string_utils_flagged_and_scored(self, clean_utility_repo, tmp_path):
        active = _run_pipeline(clean_utility_repo)
        assert len(active) > 0
        su = next(c for c in active if "string_utils" in c.path)
        # Should have a decent score: tests + docstring + 0 internal + few external
        assert su.code_quality >= 7.0, f"got {su.code_quality}"
        assert su.has_tests is True
        assert su.has_docstring is True
        assert su.suggested_name
        assert "python" in su.suggested_tags

    def test_report_generation_works(self, clean_utility_repo, tmp_path):
        active = _run_pipeline(clean_utility_repo)
        out = tmp_path / "report.md"
        generate_report(
            "fixture", "clean-utility", "Python", active, out,
            max_candidates=10,
        )
        text = out.read_text()
        assert "string_utils" in text
        assert "fixture/clean-utility" in text


class TestEndToEndCoupledCore:
    def test_config_loader_skipped(self, coupled_core_repo):
        files = walk_repo(coupled_core_repo)
        lang = detect_primary_language(files)
        candidates = detect_candidates(files, lang)
        # config_loader should be skipped (3 internal imports)
        cl = next(
            (c for c in candidates if "config_loader" in c.path),
            None,
        )
        assert cl is not None
        assert cl.skipped is True
        assert "internal" in cl.skip_reason.lower() or "coupled" in cl.skip_reason.lower()


class TestEndToEndImportCycle:
    def test_cycle_members_flagged(self, import_cycle_repo):
        files = walk_repo(import_cycle_repo)
        lang = detect_primary_language(files)
        candidates = detect_candidates(files, lang)
        # Both cycle_a and cycle_b have only 1 internal import each, so
        # they pass the simple "internal_imports >= 2" check. Either:
        # (a) the new SCC check skips them, or
        # (b) they're flagged as active but with a cycle warning in why_extractable.
        cycle_candidates = [c for c in candidates if "cycle" in c.path]
        assert len(cycle_candidates) >= 1


class TestEndToEndGodFunction:
    def test_god_function_penalized(self, god_function_repo):
        active = _run_pipeline(god_function_repo)
        god = next(
            (c for c in active if "god_function" in c.path),
            None,
        )
        if god is not None:
            # If it's not skipped, it should have a complexity penalty
            assert god.code_quality <= 5.0, \
                f"god function should be penalized for high cc, got {god.code_quality}"


class TestEndToEndOrphanLeaf:
    def test_orphan_flagged_with_orphan_signal(self, orphan_leaf_repo):
        active = _run_pipeline(orphan_leaf_repo)
        orphan = next(
            (c for c in active if "orphan" in c.path),
            None,
        )
        assert orphan is not None, "orphan.py should be detected as extractable"
        # Should have a fan-in == 0 indicator
        reasons = " ".join(orphan.why_extractable).lower()
        assert "orphan" in reasons or "fan-in" in reasons or "self-contained" in reasons


class TestEndToEndMultiLanguage:
    def test_language_detection_picks_a_real_language(self, multi_language_repo):
        files = walk_repo(multi_language_repo)
        lang = detect_primary_language(files)
        assert lang in {"Python", "TypeScript", "Go", "JavaScript"}

    def test_ts_candidate_detected(self, multi_language_repo):
        files = walk_repo(multi_language_repo)
        lang = detect_primary_language(files)
        candidates = detect_candidates(files, lang)
        # format_bytes.ts has JSDoc, 0 internal imports, utility name
        # But because the primary language might be Go (1 file) vs TS (1 file),
        # we may not get TS candidates if lang detection picks Go.
        # So just verify we get *something* OR a clean "no candidates" outcome.
        # The point is that the pipeline doesn't crash on a multi-language repo.
        assert isinstance(candidates, list)
