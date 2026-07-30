"""People Helper — Find what's extractable from your code.

Public API:
    detect_candidates  — find extractable candidates in a list of files
    generate_report    — render candidates as a markdown report
    extract_candidates — copy candidates to disk with package scaffolds
    score_candidate    — score a candidate on 6 dimensions
    walk_repo          — walk a repo dir and return file dicts
    parse_repo_arg     — parse a GitHub repo URL or owner/name string
    check_pat_scope    — verify a GitHub PAT has read-only scope
    Candidate          — dataclass for a single extractable candidate
    SimilarProject     — dataclass for a GitHub search result
    __version__        — package version string
"""

__version__ = "1.0.0"

# Re-export the public API so library users can `from people_helper import ...`
# without reaching into internal modules.
from .detection import detect_candidates  # noqa: E402
from .extractor import extract_candidate, extract_candidates  # noqa: E402
from .models import Candidate, SimilarProject  # noqa: E402
from .pat import check_pat_scope  # noqa: E402
from .report import generate_report  # noqa: E402
from .scoring import score_candidate  # noqa: E402
from .search import build_search_query, compute_differentiators, github_search_repositories  # noqa: E402
from .walker import clone_repo_shallow, detect_primary_language, parse_repo_arg, walk_repo  # noqa: E402

__all__ = [
    "__version__",
    "Candidate",
    "SimilarProject",
    "detect_candidates",
    "generate_report",
    "extract_candidates",
    "extract_candidate",
    "score_candidate",
    "walk_repo",
    "parse_repo_arg",
    "clone_repo_shallow",
    "detect_primary_language",
    "check_pat_scope",
    "github_search_repositories",
    "build_search_query",
    "compute_differentiators",
]
