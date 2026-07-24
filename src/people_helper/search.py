"""Stage 5: GitHub search for similar projects."""

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from .config import GITHUB_API
from .models import SimilarProject

# Repos pushed within the last 24 months count as "active".
# Computed at module load — fine for a CLI run.
TWENTY_FOUR_MONTHS_AGO = (datetime.now(timezone.utc) - timedelta(days=730)).strftime("%Y-%m-%d")


def github_search_repositories(
    query: str,
    language: str,
    pat: str,
    min_stars: int = 5,
    limit: int = 5,
) -> list:
    """
    Search GitHub for similar projects.
    Filters by: language, min stars, and recency (last 24 months).
    Returns a list of SimilarProject objects.
    """
    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
    }
    full_query = f"{query} language:{language} stars:>={min_stars} pushed:>={TWENTY_FOUR_MONTHS_AGO}"

    try:
        r = httpx.get(
            f"{GITHUB_API}/search/repositories",
            params={"q": full_query, "sort": "stars", "per_page": limit},
            headers=headers,
            timeout=15,
        )
    except httpx.HTTPError as e:
        print(f"  [warn] search network error: {e}", file=sys.stderr)
        return []

    if r.status_code == 403:
        msg = r.json().get("message", "")
        print(f"  [warn] rate limited: {msg}", file=sys.stderr)
        return []
    if r.status_code == 422:
        msg = r.json().get("message", "")
        print(f"  [warn] search validation error: {msg}", file=sys.stderr)
        return []
    if r.status_code != 200:
        print(f"  [warn] search status {r.status_code}", file=sys.stderr)
        return []

    items = r.json().get("items", [])
    results = []
    for it in items:
        results.append(SimilarProject(
            full_name=it["full_name"],
            html_url=it["html_url"],
            stars=it["stargazers_count"],
            description=(it.get("description") or "").strip(),
            pushed_at=it.get("pushed_at", "")[:10],
            license=(it.get("license") or {}).get("spdx_id", "?"),
            open_issues=it.get("open_issues_count", 0),
            forks=it.get("forks_count", 0),
            language=(it.get("language") or ""),
        ))
    return results


def build_search_query(candidate) -> str:
    """
    Build a GitHub search query from the candidate's path and docstring.
    Extracts meaningful keywords, filters out common noise words.
    """
    stem = Path(candidate.path).stem

    # Extract words from docstring, filtering noise
    noise_words = {
        "the", "this", "that", "module", "class", "function", "and",
        "for", "with", "from", "file", "import", "export", "const",
        "let", "var", "return", "package", "type", "struct", "interface",
        "impl", "def", "func", "pub", "fn", "use", "mod", "crate",
    }
    words = []
    if candidate.docstring_snippet:
        all_words = re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", candidate.docstring_snippet)
        words = [w for w in all_words if w.lower() not in noise_words][:5]

    # Combine stem + meaningful docstring words
    query_parts = [stem] + words
    return " ".join(query_parts)


def compute_differentiators(candidate) -> list:
    """
    Generate differentiators by comparing the candidate's traits
    against its similar projects.

    New in v0.3: looks at ALL similar projects, not just the top one,
    to compute median maintenance health + niche gaps.
    """
    if not candidate.similar_projects:
        return ["No similar projects found with 5+ stars and recent activity — potential first-mover opportunity"]

    differentiators = []
    top = candidate.similar_projects[0]

    # Compare stars/activity of the TOP result
    if top.stars > 1000:
        differentiators.append(
            f"The top result ({top.full_name}) has {top.stars:,} stars — your implementation would need a clear advantage in approach or niche to compete"
        )
    elif top.stars < 50:
        differentiators.append(
            f"The closest match ({top.full_name}) has only {top.stars} stars — the space is underserved and your implementation could fill gaps"
        )

    # Compare language
    if candidate.language and top.language and candidate.language != top.language:
        differentiators.append(
            f"Your implementation is in {candidate.language} while {top.full_name} is in {top.language} — different language ecosystems have different needs"
        )

    # Compare freshness
    if top.pushed_at:
        try:
            top_date = datetime.strptime(top.pushed_at, "%Y-%m-%d")
            months_inactive = (datetime.now() - top_date).days // 30
            if months_inactive > 12:
                differentiators.append(
                    f"{top.full_name} hasn't been pushed to in {months_inactive} months — potential maintenance gap you could fill"
                )
            elif months_inactive < 3:
                differentiators.append(
                    f"{top.full_name} is actively maintained (last push {months_inactive} month(s) ago) — study their approach for differentiation"
                )
        except ValueError:
            pass

    # Compare license
    if candidate.suggested_license and top.license:
        if top.license not in {"MIT", "?", candidate.suggested_license}:
            differentiators.append(
                f"{top.full_name} uses {top.license} license — your MIT-licensed version may appeal to users wanting permissive licensing"
            )

    # Code-level comparison hints
    if candidate.has_tests and top.open_issues > 20:
        differentiators.append(
            f"Your candidate has tests while {top.full_name} has {top.open_issues} open issues — reliability could be a differentiator"
        )

    # --- New v0.3: aggregate stats across ALL similar projects ---
    all_projs = candidate.similar_projects

    # Niche gap: how many of the similar projects are stale (>12 months)?
    stale_count = 0
    for p in all_projs:
        if p.pushed_at:
            try:
                pdate = datetime.strptime(p.pushed_at, "%Y-%m-%d")
                if (datetime.now() - pdate).days > 365:
                    stale_count += 1
            except ValueError:
                pass
    if len(all_projs) >= 3 and stale_count >= len(all_projs) * 0.6:
        differentiators.append(
            f"{stale_count}/{len(all_projs)} similar projects haven't been pushed in over a year — clear opening for an actively-maintained alternative"
        )

    # Stars-per-fork engagement quality (top result only — others may be noisy)
    if top.stars > 100 and top.forks > 0:
        ratio = top.stars / top.forks
        if ratio > 50:
            differentiators.append(
                f"{top.full_name} has {top.stars:,} stars but only {top.forks} forks (ratio {ratio:.0f}:1) — high curiosity, low real usage. Your implementation can win on actual usability."
            )
        elif ratio < 5:
            differentiators.append(
                f"{top.full_name} has {top.forks} forks vs {top.stars:,} stars (ratio {ratio:.1f}:1) — high real-usage signal; the market is proven but you'd be entering a competitive fork-and-extend space"
            )

    if not differentiators:
        differentiators.append(
            f"Compared to {top.full_name} ({top.stars} stars): review both codebases to identify specific implementation differences in approach, API design, or edge case handling"
        )

    return differentiators
