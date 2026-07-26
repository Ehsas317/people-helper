"""Data structures for People Helper."""

from dataclasses import dataclass, field


@dataclass
class Candidate:
    path: str
    language: str
    loc: int
    has_tests: bool
    has_docstring: bool
    internal_imports: int
    external_imports: int
    filename_score: float
    # Scoring dimensions (0-10)
    code_quality: float = 0.0
    uniqueness: float = 0.0
    demand_signal: float = 0.0
    relevance: float = 0.0
    usefulness: float = 0.0
    maintainability: float = 0.0
    combined_score: float = 0.0
    ship_effort_hours: float = 0.0
    # Content metadata
    docstring_snippet: str = ""
    first_lines: str = ""
    what_it_does: str = ""
    why_extractable: list = field(default_factory=list)
    similar_projects: list = field(default_factory=list)
    differentiators: list = field(default_factory=list)
    suggested_name: str = ""
    # Default is REVIEW-NEEDED — user must explicitly choose a license.
    # Auto-assigning MIT would be a compliance bug for GPL/AGPL sources.
    suggested_license: str = "REVIEW-NEEDED"
    suggested_tags: list = field(default_factory=list)
    # Deep signals (computed from FULL content during detection)
    complexity: int = 0
    fan_in: int = -1
    in_cycle: bool = False
    dependency_weight: int = 0  # 0=stdlib, 1=light, 3=heavy
    api_surface_count: int = 0
    is_stdlib_only: bool = False
    has_project_specific_refs: bool = False
    function_names: list = field(default_factory=list)  # public function/class names
    comment_ratio: float = 0.0  # 0.0-1.0
    # Extraction verification (the difference between "looks standalone" and "IS standalone")
    relative_imports: list = field(default_factory=list)  # sibling module names from relative imports
    sibling_paths: list = field(default_factory=list)  # resolved sibling files that exist in repo
    missing_siblings: list = field(default_factory=list)  # sibling names NOT found in repo
    extraction_type: str = "single"  # "single" | "multi" | "blocked"
    source_has_license: bool = True  # whether the source repo has a license file
    skipped: bool = False
    skip_reason: str = ""
    # External check results (for future --check feature; populated by checks.py)
    check_results: list = field(default_factory=list)


@dataclass
class SimilarProject:
    full_name: str
    html_url: str
    stars: int
    description: str
    pushed_at: str
    license: str
    open_issues: int = 0
    forks: int = 0
    language: str = ""