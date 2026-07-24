"""GitHub search for similar projects."""
import re, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import httpx
from .config import GITHUB_API
from .models import SimilarProject

TWENTY_FOUR_MONTHS_AGO = (datetime.now(timezone.utc) - timedelta(days=730)).strftime("%Y-%m-%d")


def github_search_repositories(query, language, pat, min_stars=5, limit=5):
    headers = {"Authorization": f"Bearer {pat}", "Accept": "application/vnd.github+json"}
    full_query = f"{query} language:{language} stars:>={min_stars} pushed:>={TWENTY_FOUR_MONTHS_AGO}"
    try:
        r = httpx.get(f"{GITHUB_API}/search/repositories", params={"q": full_query, "sort": "stars", "per_page": limit}, headers=headers, timeout=15)
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
        print(f"  [warn] search {r.status_code}: {msg}", file=sys.stderr)
        return []
    if r.status_code != 200:
        return []
    if not isinstance(data, dict):
        return []
    items = data.get("items", [])
    if not isinstance(items, list):
        return []
    results = []
    for it in items:
        if not isinstance(it, dict):
            continue
        # Skip malformed items missing required fields (avoids KeyError)
        if not all(k in it for k in ("full_name", "html_url", "stargazers_count")):
            continue
        try:
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
        except (KeyError, TypeError):
            continue
    return results

def build_search_query(candidate) -> str:
    """Uses function_names (from FULL content) for specific queries."""
    stem = Path(candidate.path).stem
    generic = {"util","utils","helper","helpers","common","lib","tool","tools","misc","mod","init","types","conf"}
    parts = [stem] if stem.lower() not in generic else []
    noise = {"the","this","that","module","class","function","and","for","with","from","file","import","export","const","let","var","return","package","type","struct","interface","impl","def","func","pub","fn","use","mod","crate","util","utils","helper","helpers","common","lib","tool","future"}
    # Use function_names (from FULL content, not first_lines)
    func_names = [n.lower() for n in candidate.function_names if n.lower() not in noise and len(n) >= 4][:2]
    if func_names:
        parts.extend(func_names)
    else:
        if candidate.docstring_snippet:
            words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", candidate.docstring_snippet) if w.lower() not in noise][:2]
            parts.extend(words)
        if candidate.first_lines:
            imports = []
            for m in re.finditer(r"^\s*(?:from|import)\s+([\w.]+)", candidate.first_lines, re.MULTILINE):
                mod = m.group(1).split(".")[0].lower()
                if mod not in noise and mod not in imports and len(mod) >= 3: imports.append(mod)
            for m in re.finditer(r"(?:from|require\()\s*['\"]([\w@/\-]+)['\"]", candidate.first_lines):
                mod = m.group(1).lstrip("@").split("/")[0].lower()
                if mod not in noise and mod not in imports and len(mod) >= 3: imports.append(mod)
            parts.extend(imports[:2])
    return " ".join(parts) if parts else stem

def compute_differentiators(candidate) -> list:
    if not candidate.similar_projects:
        return ["No similar projects found — potential first-mover opportunity"]
    diffs, top = [], candidate.similar_projects[0]
    if top.stars > 1000: diffs.append(f"Top result ({top.full_name}) has {top.stars:,} stars — need clear advantage")
    elif top.stars < 50: diffs.append(f"Closest match ({top.full_name}) has only {top.stars} stars — underserved space")
    if candidate.language and top.language and candidate.language != top.language:
        diffs.append(f"Yours is {candidate.language}, top result is {top.language}")
    if top.pushed_at:
        try:
            # Use timezone-aware UTC for consistency with TWENTY_FOUR_MONTHS_AGO
            months = (datetime.now(timezone.utc) - datetime.strptime(top.pushed_at, "%Y-%m-%d").replace(tzinfo=timezone.utc)).days // 30
            if months > 12: diffs.append(f"{top.full_name} hasn't been pushed in {months} months — maintenance gap")
            elif months < 3: diffs.append(f"{top.full_name} actively maintained — study for differentiation")
        except ValueError: pass
    if candidate.has_tests and top.open_issues > 20:
        diffs.append(f"Yours has tests, {top.full_name} has {top.open_issues} open issues — reliability advantage")
    stale = sum(1 for p in candidate.similar_projects if p.pushed_at and (datetime.now(timezone.utc) - datetime.strptime(p.pushed_at, "%Y-%m-%d").replace(tzinfo=timezone.utc)).days > 365)
    if len(candidate.similar_projects) >= 3 and stale >= len(candidate.similar_projects) * 0.6:
        diffs.append(f"{stale}/{len(candidate.similar_projects)} similar projects stale — clear opening")
    if not diffs: diffs.append(f"Compare with {top.full_name} ({top.stars} stars) for differentiation")
    return diffs
