"""Data structures for People Helper."""

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Candidate:
    """A potential extractable component."""
    path: str
    language: str
    loc: int
    has_tests: bool
    has_docstring: bool
    internal_imports: int
    external_imports: int
    filename_score: float
    code_quality: float = 0.0
    uniqueness: float = 0.0
    demand_signal: float = 0.0
    ship_effort_hours: float = 0.0
    combined_score: float = 0.0
    docstring_snippet: str = ""
    first_lines: str = ""
    what_it_does: str = ""
    why_extractable: list = field(default_factory=list)
    similar_projects: list = field(default_factory=list)
    differentiators: list = field(default_factory=list)
    suggested_name: str = ""
    suggested_license: str = "MIT"
    suggested_tags: list = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""

    def to_dict(self) -> dict:
        """Serialize to dict, converting list fields properly."""
        d = asdict(self)
        return d


@dataclass
class SimilarProject:
    """A GitHub repo found via search."""
    full_name: str
    html_url: str
    stars: int
    description: str
    pushed_at: str
    license: str
    open_issues: int = 0
    forks: int = 0
    language: str = ""
