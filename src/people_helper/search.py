"""Stage 7: GitHub search for similar projects.

Rate-limit handling: On HTTP 403/422 (rate limit / bad query), we return a
sentinel `RATE_LIMITED` instead of an empty list. The caller (people_helper.py)
detects this and passes `similar_count=-1` to score_candidate, which yields a
neutral uniqueness score of 5.0 (not a misleading 8.0 "truly unique").
"""

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from .config import GITHUB_API
from .models import Candidate, SimilarProject

# Sentinel returned by github_search_repositories when the search rate limit
# is hit. Callers should check `if results is RATE_LIMITED:` and treat it as
# "unknown" (not "no results").
RATE_LIMITED = "__rate_limited__"

TWENTY_FOUR_MONTHS_AGO = (datetime.now(timezone.utc) - timedelta(days=730)).strftime("%Y-%m-%d")


def github_search_repositories(
    query: str,
    language: str,
    pat: str,
    min_stars: int = 5,
    limit: int = 5,
) -> list[SimilarProject] | str:
    """Search GitHub for repositories matching the query.

    Returns:
        - List[SimilarProject] on success (may be empty if no matches)
        - RATE_LIMITED sentinel on HTTP 403/422 (rate limit, bad query)
        - [] (empty list) on other errors (network, non-JSON, 5xx)

    The caller MUST check `if results is RATE_LIMITED` to distinguish
    "search failed" from "search succeeded with no results".
    """
    headers = {"Authorization": f"Bearer {pat}", "Accept": "application/vnd.github+json"}
    full_query = f"{query} language:{language} stars:>={min_stars} pushed:>={TWENTY_FOUR_MONTHS_AGO}"
    try:
        r = httpx.get(
            f"{GITHUB_API}/search/repositories",
            params={"q": full_query, "sort": "stars", "per_page": limit},
            headers=headers,
            timeout=15,
        )
    except httpx.HTTPError as e:
        print(f"  [warn] search error: {e}", file=sys.stderr)
        return []
    # Parse JSON safely — proxies/CDNs may return HTML error pages
    try:
        data = r.json()
    except Exception:
        print(f"  [warn] search returned non-JSON response (status {r.status_code})", file=sys.stderr)
        return []
    if r.status_code in (403, 422):
        msg = data.get("message", "") if isinstance(data, dict) else ""
        print(
            f"  [warn] search {r.status_code}: {msg} — uniqueness will be marked 'unknown' "
            f"(neutral 5.0), not 'truly unique'.",
            file=sys.stderr,
        )
        return RATE_LIMITED
    if r.status_code != 200:
        print(f"  [warn] search returned status {r.status_code}", file=sys.stderr)
        return []
    if not isinstance(data, dict):
        return []
    items = data.get("items", [])
    if not isinstance(items, list):
        return []
    results: list[SimilarProject] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        # Skip malformed items missing required fields (avoids KeyError)
        if not all(k in it for k in ("full_name", "html_url", "stargazers_count")):
            continue
        try:
            results.append(
                SimilarProject(
                    full_name=it["full_name"],
                    html_url=it["html_url"],
                    stars=it["stargazers_count"],
                    description=(it.get("description") or "").strip(),
                    pushed_at=it.get("pushed_at", "")[:10],
                    license=(it.get("license") or {}).get("spdx_id", "?"),
                    open_issues=it.get("open_issues_count", 0),
                    forks=it.get("forks_count", 0),
                    language=(it.get("language") or ""),
                )
            )
        except (KeyError, TypeError):
            continue
    return results


def build_search_query(candidate: Candidate) -> str:
    """Build a GitHub search query from candidate signals.

    Uses function names from the FULL content (most specific). Falls back to
    docstring words and import module names from first_lines.
    """
    stem = Path(candidate.path).stem
    generic = {
        "util",
        "utils",
        "helper",
        "helpers",
        "common",
        "lib",
        "tool",
        "tools",
        "misc",
        "mod",
        "init",
        "types",
        "conf",
    }
    parts = [stem] if stem.lower() not in generic else []
    noise = {
        "the",
        "this",
        "that",
        "module",
        "class",
        "function",
        "and",
        "for",
        "with",
        "from",
        "file",
        "import",
        "export",
        "const",
        "let",
        "var",
        "return",
        "package",
        "type",
        "struct",
        "interface",
        "impl",
        "def",
        "func",
        "pub",
        "fn",
        "use",
        "mod",
        "crate",
        "util",
        "utils",
        "helper",
        "helpers",
        "common",
        "lib",
        "tool",
        "future",
    }
    # Use function_names (from FULL content)
    func_names = [n.lower() for n in candidate.function_names if n.lower() not in noise and len(n) >= 4][:2]
    if func_names:
        parts.extend(func_names)
    else:
        if candidate.docstring_snippet:
            words = [
                w
                for w in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", candidate.docstring_snippet)
                if w.lower() not in noise
            ][:2]
            parts.extend(words)
        if candidate.first_lines:
            imports = []
            for m in re.finditer(r"^\s*(?:from|import)\s+([\w.]+)", candidate.first_lines, re.MULTILINE):
                mod = m.group(1).split(".")[0].lower()
                if mod not in noise and mod not in imports and len(mod) >= 3:
                    imports.append(mod)
            for m in re.finditer(r"(?:from|require\()\s*['\"]([\w@/\-]+)['\"]", candidate.first_lines):
                mod = m.group(1).lstrip("@").split("/")[0].lower()
                if mod not in noise and mod not in imports and len(mod) >= 3:
                    imports.append(mod)
            parts.extend(imports[:2])
    return " ".join(parts) if parts else stem


def _safe_months_since(pushed_at: str) -> int | None:
    """Safely parse pushed_at and return months since, or None on parse failure."""
    if not pushed_at:
        return None
    try:
        dt = datetime.strptime(pushed_at, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None
    return (datetime.now(timezone.utc) - dt).days // 30


def compute_differentiators(candidate: Candidate) -> list[str]:
    """Compute differentiation points vs similar projects.

    Handles RATE_LIMITED sentinel: if similar_projects is RATE_LIMITED, returns
    a 'search unavailable' message instead of 'first-mover opportunity'.
    """
    if candidate.similar_projects is RATE_LIMITED or candidate.similar_projects == RATE_LIMITED:
        return ["Search rate-limited — uniqueness unknown (treated as neutral 5.0)"]
    if not candidate.similar_projects:
        return ["No similar projects found — potential first-mover opportunity"]
    diffs: list[str] = []
    top = candidate.similar_projects[0]
    if top.stars > 1000:
        diffs.append(f"Top result ({top.full_name}) has {top.stars:,} stars — need clear advantage")
    elif top.stars < 50:
        diffs.append(f"Closest match ({top.full_name}) has only {top.stars} stars — underserved space")
    if candidate.language and top.language and candidate.language != top.language:
        diffs.append(f"Yours is {candidate.language}, top result is {top.language}")
    months = _safe_months_since(top.pushed_at)
    if months is not None:
        if months > 12:
            diffs.append(f"{top.full_name} hasn't been pushed in {months} months — maintenance gap")
        elif months < 3:
            diffs.append(f"{top.full_name} actively maintained — study for differentiation")
    if candidate.has_tests and top.open_issues > 20:
        diffs.append(f"Yours has tests, {top.full_name} has {top.open_issues} open issues — reliability advantage")
    # Stale count using the safe parser
    stale = sum(
        1
        for p in candidate.similar_projects
        if _safe_months_since(p.pushed_at) is not None and _safe_months_since(p.pushed_at) > 12
    )  # type: ignore[operator]
    if len(candidate.similar_projects) >= 3 and stale >= len(candidate.similar_projects) * 0.6:
        diffs.append(f"{stale}/{len(candidate.similar_projects)} similar projects stale — clear opening")
    if not diffs:
        diffs.append(f"Compare with {top.full_name} ({top.stars} stars) for differentiation")
    return diffs
