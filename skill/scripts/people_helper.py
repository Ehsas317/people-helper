#!/usr/bin/env python3
"""
people_helper.py — standalone CLI implementation of the People Helper skill.

Runs the same workflow described in SKILL.md (clone -> score -> search GitHub
-> report) without needing an agent session. Useful for re-running the
analysis later, or wiring into CI.

Usage:
    export PEOPLE_HELPER_PAT=github_pat_xxx
    python people_helper.py owner/repo [--min-stars 5] [--output report.md]

Trust boundary: this script only ever reads. It clones with --depth 1 to a
temp directory, deletes that directory when done (even on error), and the
only network calls it makes are `git clone` against github.com and read-only
GET requests to api.github.com. It never writes to the target repo.

Scoring: combined = 0.5 * code_quality + 0.3 * uniqueness + 0.2 * demand_signal
"""

import argparse
import ast
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Missing dependency 'requests'. Install with: pip install -r requirements.txt")

GITHUB_API = "https://api.github.com"
UTILITY_NAME_RE = re.compile(r"(util|helper|common|lib)", re.IGNORECASE)
MIN_LOC, MAX_LOC = 10, 500


# --- Scoring weights (must match SKILL.md and heuristics.md) ---
CODE_QUALITY_WEIGHT = 0.5
UNIQUENESS_WEIGHT = 0.3
DEMAND_SIGNAL_WEIGHT = 0.2


def parse_repo_arg(arg: str) -> tuple[str, str]:
    """Accepts owner/name, a full https URL, or an ssh URL. Returns (owner, name)."""
    arg = arg.strip()
    if arg.startswith("git@"):
        path = arg.split(":", 1)[1]
    elif arg.startswith("http"):
        path = arg.split("github.com/", 1)[1]
    else:
        path = arg
    path = path.removesuffix(".git").strip("/")
    owner, name = path.split("/", 1)
    return owner, name


def clone_repo(owner: str, name: str, pat: str, workdir: Path) -> Path:
    dest = workdir / name
    url = f"https://x-access-token:{pat}@github.com/{owner}/{name}.git"
    result = subprocess.run(
        ["git", "clone", "--depth", "1", "--quiet", url, str(dest)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        scrubbed = result.stderr.replace(pat, "***")
        raise RuntimeError(f"git clone failed: {scrubbed}")
    return dest


def detect_primary_language(repo_dir: Path) -> str:
    ext_counts: dict[str, int] = {}
    ext_to_lang = {
        ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript",
        ".js": "JavaScript", ".jsx": "JavaScript", ".go": "Go",
        ".rs": "Rust", ".java": "Java",
    }
    for path in repo_dir.rglob("*"):
        if path.is_file() and path.suffix in ext_to_lang:
            if ".git" in path.parts or "node_modules" in path.parts:
                continue
            lang = ext_to_lang[path.suffix]
            ext_counts[lang] = ext_counts.get(lang, 0) + 1
    if not ext_counts:
        return "Unknown"
    return max(ext_counts, key=lambda k: ext_counts[k])


def candidate_files(repo_dir: Path, language: str) -> list[Path]:
    suffix = {"Python": ".py", "TypeScript": ".ts", "JavaScript": ".js",
              "Go": ".go", "Rust": ".rs", "Java": ".java"}.get(language, ".py")
    skip_dirs = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}
    out = []
    for path in repo_dir.rglob(f"*{suffix}"):
        if any(part in skip_dirs for part in path.parts):
            continue
        if "test" in path.stem.lower():
            continue
        out.append(path)
    return out


def score_python_file(path: Path, repo_dir: Path) -> dict | None:
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
        loc = len(source.splitlines())
    except OSError:
        return None

    if not (MIN_LOC <= loc <= MAX_LOC):
        return None

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    has_docstring = ast.get_docstring(tree) is not None
    internal_imports = 0
    external_imports = 0
    repo_top_level = {p.name for p in repo_dir.iterdir() if p.is_dir()}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in repo_top_level:
                    internal_imports += 1
                else:
                    external_imports += 1
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                internal_imports += 1
            elif node.module and node.module.split(".")[0] in repo_top_level:
                internal_imports += 1
            else:
                external_imports += 1

    has_test = (path.parent / "tests" / f"test_{path.name}").exists() or \
               any(repo_dir.rglob(f"test_{path.stem}.py")) or \
               any(repo_dir.rglob(f"{path.stem}_test.py"))
    utility_name = bool(UTILITY_NAME_RE.search(path.stem))

    # code_quality: 0-10 scale
    code_quality = 0.0
    if has_test:
        code_quality += 3
    if has_docstring:
        code_quality += 2
    if internal_imports == 0:
        code_quality += 2
    elif internal_imports == 1:
        code_quality += 1
    if external_imports <= 3:
        code_quality += 2
    elif external_imports <= 5:
        code_quality += 1
    if utility_name:
        code_quality += 1
    code_quality = min(code_quality, 10.0)

    if internal_imports > 2 or code_quality < 4:
        return None

    return {
        "path": path,
        "loc": loc,
        "has_docstring": has_docstring,
        "has_test": has_test,
        "internal_imports": internal_imports,
        "external_imports": external_imports,
        "code_quality": code_quality,
        "docstring": (ast.get_docstring(tree) or "").split("\n")[0],
    }


def ship_effort_hours(loc: int) -> float:
    if loc < 50:
        return 1.5
    if loc < 150:
        return 3.0
    if loc < 300:
        return 6.0
    return 16.0


def search_github(query: str, language: str, pat: str, min_stars: int) -> dict:
    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    q = f"{query} language:{language} stars:>={min_stars} pushed:>2024-07-23"
    resp = requests.get(
        f"{GITHUB_API}/search/repositories",
        headers=headers,
        params={"q": q, "sort": "stars", "order": "desc", "per_page": 5},
        timeout=15,
    )
    if resp.status_code == 403:
        remaining = resp.headers.get("X-RateLimit-Remaining", "?")
        raise RuntimeError(f"GitHub API rate limited (remaining={remaining}).")
    resp.raise_for_status()
    return resp.json()


def uniqueness_score(total_count: int) -> float:
    if total_count == 0:
        return 8.0
    if total_count <= 2:
        return 6.0
    if total_count <= 5:
        return 4.0
    return 2.0


def demand_signal_score(similar_items: list) -> float:
    """Compute demand signal from similar projects' stars/forks/issues."""
    if not similar_items:
        return 5.0  # Niche but real demand
    total_signal = 0.0
    weight_sum = 0.0
    for i, repo in enumerate(similar_items):
        weight = 1.0 / (i + 1)
        stars = repo.get("stargazers_count", 0) or 0
        forks = repo.get("forks_count", 0) or 0
        issues = repo.get("open_issues_count", 0) or 0
        star_signal = min(10.0, stars / 100.0)
        fork_signal = min(5.0, forks / 50.0)
        issue_signal = min(3.0, issues / 10.0)
        total_signal += weight * (star_signal + fork_signal + issue_signal)
        weight_sum += weight
    avg = total_signal / weight_sum if weight_sum > 0 else 0
    return min(10.0, avg / 1.8)


def build_report(repo_owner: str, repo_name: str, language: str,
                  scored: list[dict], skipped_count: int) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "# People Helper Report", "",
        f"**Repo:** {repo_owner}/{repo_name}",
        f"**Generated:** {now}",
        f"**Primary language:** {language}",
        f"**Candidates analyzed:** {len(scored) + skipped_count}",
        f"**Top candidates:** {len(scored)}",
        f"**Scoring:** {CODE_QUALITY_WEIGHT} x code quality + {UNIQUENESS_WEIGHT} x uniqueness + {DEMAND_SIGNAL_WEIGHT} x demand signal",
        "", "---", "", "## Top candidates", "",
    ]
    for i, c in enumerate(sorted(scored, key=lambda x: -x["combined_score"]), start=1):
        rel_path = c["path"]
        lines += [
            f"### {i}. `{c['path'].name}` — Combined score: {c['combined_score']:.1f}/10",
            "",
            f"**Location:** `{rel_path}`",
            f"**Language:** {language}",
            f"**Code quality:** {c['code_quality']:.0f}/10 (weight: {int(CODE_QUALITY_WEIGHT*100)}%)",
            f"**Uniqueness:** {c['uniqueness']:.0f}/10 (weight: {int(UNIQUENESS_WEIGHT*100)}%)",
            f"**Demand signal:** {c['demand_signal']:.0f}/10 (weight: {int(DEMAND_SIGNAL_WEIGHT*100)}%)",
            f"**Estimated ship effort:** {c['ship_effort']}h",
            "",
            "**What it does:**", c.get("docstring") or "(no docstring found)", "",
            "**Similar projects on GitHub:**",
        ]
        if c["similar"]:
            for repo in c["similar"]:
                lines.append(
                    f"- [`{repo['full_name']}`]({repo['html_url']}) — "
                    f"{repo['stargazers_count']}⭐, last commit {repo['pushed_at'][:10]}"
                )
        else:
            lines.append("- No similar projects found with 5+ stars and recent activity.")
        lines += ["", "---", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repo", help="owner/name, https URL, or ssh URL")
    parser.add_argument("--min-stars", type=int, default=5)
    parser.add_argument("--output", default="people_helper_report.md")
    parser.add_argument("--max-candidates-searched", type=int, default=10,
                         help="cap GitHub search calls to stay well under rate limits")
    args = parser.parse_args()

    pat = os.environ.get("PEOPLE_HELPER_PAT")
    if not pat:
        sys.exit("Set PEOPLE_HELPER_PAT to a fine-grained, read-only "
                  "(Contents: Read, Metadata: Read) GitHub PAT before running this.")

    owner, name = parse_repo_arg(args.repo)
    workdir = Path(tempfile.mkdtemp(prefix="people-helper-"))
    try:
        print(f"Cloning {owner}/{name}...", file=sys.stderr)
        repo_dir = clone_repo(owner, name, pat, workdir)

        language = detect_primary_language(repo_dir)
        print(f"Primary language: {language}", file=sys.stderr)
        if language != "Python":
            print("Note: only Python scoring is fully implemented in this script. "
                  "See references/heuristics.md and run the analysis manually "
                  "(via the agent skill) for other languages.", file=sys.stderr)

        files = candidate_files(repo_dir, language)
        scored, skipped = [], 0
        for f in files:
            result = score_python_file(f, repo_dir) if language == "Python" else None
            if result is None:
                skipped += 1
                continue
            result["ship_effort"] = ship_effort_hours(result["loc"])
            scored.append(result)

        scored.sort(key=lambda c: -c["code_quality"])
        top = scored[: args.max_candidates_searched]

        for c in top:
            query = re.sub(r"[^a-zA-Z0-9 ]", " ", c["path"].stem).strip()
            try:
                results = search_github(query, language.lower(), pat, args.min_stars)
            except RuntimeError as e:
                print(f"  search skipped for {c['path'].name}: {e}", file=sys.stderr)
                results = {"total_count": 0, "items": []}
            c["uniqueness"] = uniqueness_score(results["total_count"])
            c["similar"] = results["items"][:5]
            c["demand_signal"] = demand_signal_score(c["similar"])
            c["combined_score"] = (
                CODE_QUALITY_WEIGHT * c["code_quality"]
                + UNIQUENESS_WEIGHT * c["uniqueness"]
                + DEMAND_SIGNAL_WEIGHT * c["demand_signal"]
            )
            time.sleep(2)

        report = build_report(owner, name, language, top, skipped)
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Report written to {args.output}", file=sys.stderr)

    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
