"""Shared pytest fixtures for People Helper tests."""
import sys
from pathlib import Path

import pytest

# Make the src/ package importable in tests
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

FIXTURES = ROOT / "tests" / "fixtures" / "repos"


@pytest.fixture
def clean_utility_repo():
    """A repo with a small self-contained Python utility + tests."""
    return FIXTURES / "clean-utility"


@pytest.fixture
def coupled_core_repo():
    """A repo where the candidate has 3 internal imports — should skip."""
    return FIXTURES / "coupled-core"


@pytest.fixture
def import_cycle_repo():
    """A repo with a 2-file import cycle — should be flagged by SCC."""
    return FIXTURES / "import-cycle"


@pytest.fixture
def god_function_repo():
    """A repo with a 200-LOC function of cc≈30 — should be flagged by complexity."""
    return FIXTURES / "god-function"


@pytest.fixture
def orphan_leaf_repo():
    """A repo with a self-contained module nobody imports — ideal extractable."""
    return FIXTURES / "orphan-leaf"


@pytest.fixture
def multi_language_repo():
    """A repo with Python + TS + Go files — tests language detection."""
    return FIXTURES / "multi-language"


@pytest.fixture
def all_fixture_repos():
    """All fixture repos as a dict {name: Path}."""
    return {
        "clean-utility": FIXTURES / "clean-utility",
        "coupled-core": FIXTURES / "coupled-core",
        "import-cycle": FIXTURES / "import-cycle",
        "god-function": FIXTURES / "god-function",
        "orphan-leaf": FIXTURES / "orphan-leaf",
        "multi-language": FIXTURES / "multi-language",
    }
